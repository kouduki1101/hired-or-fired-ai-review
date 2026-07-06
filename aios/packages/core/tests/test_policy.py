from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from aios_core.policy.dynamics import adjust_dynamics
from aios_core.policy.health import HealthJudge, classify_raw
from aios_core.policy.rehatch_select import select_rehatch_targets
from aios_core.policy.routing import NoRoutableSlotError, TaskMeta, route_task
from aios_core.policy.stabilization import detect_stabilization_point
from aios_core.types import (
    Cluster,
    DynamicsConfig,
    DynamicsSignal,
    HealthStatus,
    HealthThresholds,
    RehatchReason,
    RehatchSelectConfig,
    RoutingConfig,
    SlotStatus,
    SlotView,
    StabilizationConfig,
    TaskDifficulty,
    TaskImportance,
)

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
TH = HealthThresholds(lower=0.2, upper=0.7, hysteresis_cycles=2)


def slot(
    sid: str,
    fitness: float | None = 0.8,
    maturity: int = 2000,
    status: SlotStatus = SlotStatus.ACTIVE,
    **kw: object,
) -> SlotView:
    return SlotView(
        slot_id=sid,
        display_id=sid,
        status=status,
        generation=1,
        maturity=maturity,
        fitness_hat=fitness,
        **kw,  # type: ignore[arg-type]
    )


class TestHealth:
    def test_raw_classification(self) -> None:
        assert classify_raw(0.1, TH) == HealthStatus.FIXED
        assert classify_raw(0.5, TH) == HealthStatus.STABLE
        assert classify_raw(0.9, TH) == HealthStatus.CHAOTIC

    def test_hysteresis_requires_streak(self) -> None:
        """h=2: 1回だけの逸脱では確定状態は変わらない(発振防止)。"""
        j = HealthJudge()
        j, s = j.observe(0.5, TH)  # 初回は即確定
        assert s == HealthStatus.STABLE
        j, s = j.observe(0.1, TH)  # 1回目のFIXED → まだSTABLE
        assert s == HealthStatus.STABLE
        j, s = j.observe(0.1, TH)  # 2回連続 → FIXED確定
        assert s == HealthStatus.FIXED

    def test_streak_resets_on_flapping(self) -> None:
        j = HealthJudge()
        j, _ = j.observe(0.5, TH)
        j, _ = j.observe(0.1, TH)  # FIXED 1回目
        j, s = j.observe(0.9, TH)  # 別方向へ → streakリセット
        assert s == HealthStatus.STABLE
        j, s = j.observe(0.9, TH)  # CHAOTIC 2回連続
        assert s == HealthStatus.CHAOTIC


class TestDynamics:
    CFG = DynamicsConfig()

    def test_fixed_increases_exploration(self) -> None:
        sig = adjust_dynamics(HealthStatus.FIXED, DynamicsSignal(), self.CFG)
        assert sig.lr_correction == pytest.approx(1.5)
        assert sig.noise_amount == pytest.approx(0.05)

    def test_chaotic_converges(self) -> None:
        cur = DynamicsSignal(lr_correction=2.0, noise_amount=0.2)
        sig = adjust_dynamics(HealthStatus.CHAOTIC, cur, self.CFG)
        assert sig.lr_correction == pytest.approx(1.2)
        assert sig.noise_amount == pytest.approx(0.15)

    def test_clamped_at_limits(self) -> None:
        cur = DynamicsSignal(lr_correction=3.9, noise_amount=0.49)
        sig = adjust_dynamics(HealthStatus.FIXED, cur, self.CFG)
        assert sig.lr_correction == self.CFG.lr_max
        assert sig.noise_amount == self.CFG.noise_max

    def test_stable_relaxes_to_baseline(self) -> None:
        cur = DynamicsSignal(lr_correction=2.0, noise_amount=0.3)
        sig = adjust_dynamics(HealthStatus.STABLE, cur, self.CFG)
        assert 1.0 < sig.lr_correction < 2.0
        assert self.CFG.noise_base < sig.noise_amount < 0.3

    def test_unknown_is_noop(self) -> None:
        cur = DynamicsSignal(lr_correction=1.3, noise_amount=0.1)
        assert adjust_dynamics(HealthStatus.UNKNOWN, cur, self.CFG) == cur


class TestRehatchSelect:
    CFG = RehatchSelectConfig()

    def test_low_fitness_selected(self) -> None:
        """請求項5: 適合度が基準を満たさないモデルを更新対象に選定。"""
        slots = [slot("a", 0.9), slot("b", 0.2), *[slot(f"x{i}", 0.8) for i in range(8)]]
        sel = select_rehatch_targets(slots, NOW, self.CFG)
        assert [(s.slot_id, s.reason) for s in sel] == [("b", RehatchReason.LOW_FITNESS)]

    def test_dominant_and_overfit(self) -> None:
        """¶0158-0159: 支配的モデル・過剰適合も対象。"""
        slots = [
            slot("dom", 0.8, assign_share=0.5),
            slot("ovf", 0.99),
            *[slot(f"x{i}", 0.8) for i in range(18)],
        ]
        sel = select_rehatch_targets(slots, NOW, self.CFG)
        reasons = {s.slot_id: s.reason for s in sel}
        assert reasons["dom"] == RehatchReason.DOMINANT
        assert reasons["ovf"] == RehatchReason.OVERFIT

    def test_locked_and_cooldown_excluded(self) -> None:
        """削除保護フラグ(図7)とクールダウン中は対象外。"""
        slots = [
            slot("locked", 0.1, rehatch_lock=True),
            slot("recent", 0.1, last_rehatch_at=NOW - timedelta(hours=1)),
            slot("target", 0.1),
            *[slot(f"x{i}", 0.8) for i in range(7)],
        ]
        sel = select_rehatch_targets(slots, NOW, self.CFG)
        assert [s.slot_id for s in sel] == ["target"]

    def test_cycle_cap(self) -> None:
        """1サイクル上限 = K×10%。優先度の高い理由から採用。"""
        slots = [slot(f"low{i}", 0.1) for i in range(5)] + [
            slot(f"x{i}", 0.8) for i in range(15)
        ]  # K=20 → cap=2
        sel = select_rehatch_targets(slots, NOW, self.CFG)
        assert len(sel) == 2
        assert all(s.reason == RehatchReason.LOW_FITNESS for s in sel)

    def test_role_duplication_keeps_best(self) -> None:
        """¶0160: 酷似グループは最高適合の1体を残し他をRehatch対象化。"""
        v = np.array([1.0, 0.0, 0.0])
        states = {"dup1": v, "dup2": v * 2, "solo": np.array([0.0, 1.0, 0.0])}
        slots = [
            slot("dup1", 0.9),
            slot("dup2", 0.7),
            slot("solo", 0.8),
            *[slot(f"x{i}", 0.8) for i in range(17)],
        ]
        sel = select_rehatch_targets(slots, NOW, self.CFG, slot_states=states)
        assert [(s.slot_id, s.reason) for s in sel] == [("dup2", RehatchReason.ROLE_DUP)]


class TestRouting:
    CFG = RoutingConfig()

    def test_high_importance_to_veteran(self) -> None:
        """請求項8/図15: 高重要度→ベテラン。"""
        slots = [slot("vet", 0.9, maturity=5000), slot("rok", 0.5, maturity=10)]
        d = route_task(TaskMeta(importance=TaskImportance.HIGH), slots, self.CFG)
        assert d.chosen_slot_id == "vet"
        assert d.cluster == Cluster.VETERAN
        assert d.reason == "high_importance_to_veteran"

    def test_exploratory_to_rookie(self) -> None:
        """探索的タスクは新人優先(経験付与、¶0190)。"""
        slots = [slot("vet", 0.9, maturity=5000), slot("rok", 0.5, maturity=10)]
        d = route_task(TaskMeta(difficulty=TaskDifficulty.EXPLORATORY), slots, self.CFG)
        assert d.chosen_slot_id == "rok"
        assert d.cluster == Cluster.ROOKIE

    def test_fallback_when_no_veteran(self) -> None:
        slots = [slot("rok1", 0.5, maturity=10), slot("rok2", 0.6, maturity=20)]
        d = route_task(TaskMeta(importance=TaskImportance.HIGH), slots, self.CFG)
        assert d.reason == "veteran_unavailable_fallback"

    def test_dominance_avoidance(self) -> None:
        """割当集中スロットは候補から降格される。"""
        slots = [
            slot("busy", 0.95, maturity=5000, assign_share=0.6),
            slot("calm", 0.85, maturity=5000, assign_share=0.1),
        ]
        d = route_task(TaskMeta(importance=TaskImportance.HIGH), slots, self.CFG)
        assert d.chosen_slot_id == "calm"

    def test_decision_records_candidates(self) -> None:
        """リネージ要件: 候補スナップショットと理由が残る。"""
        slots = [slot("a"), slot("b")]
        d = route_task(TaskMeta(), slots, self.CFG)
        assert {c.slot_id for c in d.candidates} == {"a", "b"}
        assert d.reason

    def test_inactive_not_routable(self) -> None:
        slots = [slot("q", status=SlotStatus.QUARANTINED)]
        with pytest.raises(NoRoutableSlotError):
            route_task(TaskMeta(), slots, self.CFG)


class TestStabilization:
    CFG = StabilizationConfig(window=3)

    def test_detects_convergence(self) -> None:
        assert detect_stabilization_point(
            tv_drifts=[0.001] * 3,
            health_history=[HealthStatus.STABLE] * 3,
            fitness_means=[0.8, 0.8, 0.8],
            cfg=self.CFG,
        )

    def test_not_stable_health_blocks(self) -> None:
        assert not detect_stabilization_point(
            [0.001] * 3,
            [HealthStatus.STABLE, HealthStatus.FIXED, HealthStatus.STABLE],
            [0.8] * 3,
            self.CFG,
        )

    def test_rising_fitness_blocks(self) -> None:
        """適合度が上昇中(まだ適応途上)は成熟点ではない。"""
        assert not detect_stabilization_point(
            [0.001] * 3, [HealthStatus.STABLE] * 3, [0.5, 0.7, 0.9], self.CFG
        )

    def test_insufficient_data(self) -> None:
        assert not detect_stabilization_point([0.001], [HealthStatus.STABLE], [0.8], self.CFG)
