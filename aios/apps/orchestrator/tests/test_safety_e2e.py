"""安全境界のe2e(docs/07 P3 test_safety 相当、¶0231/0237)。

シナリオ: 禁止ベクトル登録 → スロットが危険方向へ変化 → 次サイクルで即時隔離
→ TVへの汚染混入なし → 復旧Rehatchで教師ベクトル方向へ復帰(世代+1)。
"""

from __future__ import annotations

import numpy as np
from aios_adapters.fake import FakeAgentAdapter
from aios_core.lineage.events import SlotEventType
from aios_core.metrics.fitness import fitness_score
from aios_core.policy.safety import NegativeCentroid
from aios_core.types import HealthThresholds, SlotStatus, StabilizationConfig
from aios_orchestrator.cycle import CycleConfig, restore_quarantined_slot, run_cycle
from aios_orchestrator.runtime import CohortRuntime, hatch_cohort

DIM = 8
TH = HealthThresholds(lower=0.05, upper=1.2, hysteresis_cycles=2)


def make_cohort() -> tuple[CohortRuntime, np.ndarray]:
    rng = np.random.default_rng(5)
    t0 = rng.normal(size=DIM)
    cohort = hatch_cohort(
        adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=100 + i),
        slot_count=8,
        initial_tv=t0,
        thresholds=TH,
        diversity=0.4,
        seed=11,
    )
    # 教師ベクトルと十分に異なる「危険方向」を作る(直交化)
    danger = rng.normal(size=DIM)
    tv = cohort.teacher_vector
    danger -= (danger @ tv) * tv
    danger /= np.linalg.norm(danger)
    cohort.negative_centroids.append(
        NegativeCentroid(label="prompt_injection", vector=tuple(danger), threshold=0.9)
    )
    return cohort, danger


class TestQuarantine:
    async def test_dangerous_slot_quarantined_immediately(self) -> None:
        cohort, danger = make_cohort()
        await run_cycle(cohort)

        victim = cohort.slots[3]
        victim.adapter.force_behavior(danger)  # type: ignore[attr-defined]

        result = await run_cycle(cohort)
        assert [q.slot_id for q in result.quarantined] == [victim.slot_id]
        assert result.quarantined[0].label == "prompt_injection"
        assert victim.status == SlotStatus.QUARANTINED
        # 隔離イベントが履歴に記録される
        assert any(e.event_type == SlotEventType.QUARANTINED for e in victim.events)

    async def test_tv_not_contaminated(self) -> None:
        """FR-SF-03: 隔離スロットの寄与はTV(EMA)に混入しない。"""
        cohort, danger = make_cohort()
        await run_cycle(cohort)

        victim = cohort.slots[0]
        victim.adapter.force_behavior(danger)  # type: ignore[attr-defined]
        await run_cycle(cohort)

        # TVが危険方向へ引っ張られていない(汚染なし)
        tv = cohort.teacher_vector
        sim_to_danger = float(tv @ danger / np.linalg.norm(tv))
        assert sim_to_danger < 0.3

    async def test_quarantined_excluded_from_rehatch_selection(self) -> None:
        cohort, danger = make_cohort()
        await run_cycle(cohort)
        victim = cohort.slots[0]
        victim.adapter.force_behavior(danger)  # type: ignore[attr-defined]
        r = await run_cycle(cohort)
        assert victim.slot_id in [q.slot_id for q in r.quarantined]
        # 以降のサイクルでRehatch対象に選ばれない(ACTIVEのみが対象)
        r2 = await run_cycle(cohort)
        assert victim.slot_id not in [o.slot_id for o in r2.rehatched]

    async def test_dry_run_does_not_quarantine(self) -> None:
        cohort, danger = make_cohort()
        await run_cycle(cohort)
        victim = cohort.slots[0]
        victim.adapter.force_behavior(danger)  # type: ignore[attr-defined]
        r = await run_cycle(cohort, CycleConfig(dry_run=True))
        assert r.quarantined == []
        assert victim.status == SlotStatus.ACTIVE


class TestRestore:
    async def test_restore_rehatches_to_safe_state(self) -> None:
        """復旧Rehatch: ID・履歴維持のまま世代+1でTV方向へ復帰し、禁止ベクトル非近接。"""
        cohort, danger = make_cohort()
        await run_cycle(cohort)
        victim = cohort.slots[2]
        victim.adapter.force_behavior(danger)  # type: ignore[attr-defined]
        await run_cycle(cohort)
        assert victim.status == SlotStatus.QUARANTINED
        original_id = victim.slot_id

        outcome = await restore_quarantined_slot(cohort, victim.slot_id)
        assert outcome.committed
        assert victim.slot_id == original_id  # 識別情報維持(請求項1)
        assert victim.status == SlotStatus.ACTIVE
        assert victim.generation == 1

        state = await victim.adapter.get_state([])
        assert fitness_score(state, cohort.teacher_vector) >= 0.5
        assert any(e.event_type == SlotEventType.RESTORED for e in victim.events)

    async def test_restore_requires_quarantined_status(self) -> None:
        cohort, _ = make_cohort()
        await run_cycle(cohort)
        active_slot = cohort.slots[0]
        try:
            await restore_quarantined_slot(cohort, active_slot.slot_id)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


class TestStabilizationPoint:
    async def test_detected_after_convergence(self) -> None:
        """FR-LC-04: TVドリフト定常化∧STABLE継続∧適合度横ばいで成熟点。"""
        cohort, _ = make_cohort()
        cfg = CycleConfig(
            stabilization=StabilizationConfig(
                window=3,
                tv_drift_eps=0.05,
                fitness_slope_eps=0.05,
                fitness_mature_level=0.5,
            )
        )
        detected = False
        for _ in range(20):
            r = await run_cycle(cohort, cfg)
            if r.stabilization_point:
                detected = True
                break
        assert detected, "収束後も成熟点が検出されなかった"
