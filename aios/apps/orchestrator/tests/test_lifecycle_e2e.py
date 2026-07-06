"""M1デモの自動化(docs/07 P1目標デモ / test_claims.py 初版)。

シナリオ:
  1. 卵層でK体のFakeエージェント群を生成(Phase1→OPERATING)
  2. 全エージェントを同質化(固着注入) → 散逸度がFIXED判定
  3. 制御ループがノイズを増加 → 挙動が拡散し STABLE へ自動復旧
  4. 教師ベクトルから逸脱したスロットが LOW_FITNESS でRehatch(in-Place)される
  5. 全過程で slot_id・履歴の連続性が維持され、ハッシュチェーンが検証可能

請求項の実施検証:
  1(ID+履歴維持のまま更新) / 3(EMA) / 4(散逸度) / 5(適合度選定) /
  6(TV基づく初期値設定) / 7(ノイズ動的調整) / 10(卵層非再入)
"""

from __future__ import annotations

import numpy as np
import pytest
from aios_adapters.fake import FakeAgentAdapter
from aios_common.errors import PhaseLockedError
from aios_core.lineage.replay import replay_slot, verify_chain
from aios_core.types import (
    CohortPhase,
    HealthStatus,
    HealthThresholds,
    RehatchReason,
    RehatchSelectConfig,
)
from aios_orchestrator.cycle import CycleConfig, run_cycle
from aios_orchestrator.runtime import CohortRuntime, guard_hatchery, hatch_cohort

DIM = 8
K = 10
TH = HealthThresholds(lower=0.05, upper=1.2, hysteresis_cycles=2)


def make_cohort(diversity: float = 0.4) -> CohortRuntime:
    rng = np.random.default_rng(99)
    t0 = rng.normal(size=DIM)
    return hatch_cohort(
        adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=1000 + i),
        slot_count=K,
        initial_tv=t0,
        thresholds=TH,
        diversity=diversity,
        seed=7,
    )


def cycle_cfg(**kw) -> CycleConfig:
    # テストではクールダウンなし(既定24hだと単一テスト内で再選定できない)
    return CycleConfig(rehatch=RehatchSelectConfig(cooldown_seconds=0), **kw)


class TestHatchery:
    def test_hatch_creates_fixed_population(self) -> None:
        """請求項10: 卵層はK体を生成し、以降OPERATINGで固定母集団となる。"""
        cohort = make_cohort()
        assert cohort.phase == CohortPhase.OPERATING
        assert len(cohort.slots) == K
        assert [s.display_id for s in cohort.slots[:3]] == ["001", "002", "003"]
        # 全スロットにSLOT_CREATEDイベントが記録済み
        assert all(len(s.events) == 1 for s in cohort.slots)

    def test_hatchery_is_non_reentrant(self) -> None:
        """請求項10: 定常運用フェーズでの追加生成はPhaseLockedError。"""
        cohort = make_cohort()
        with pytest.raises(PhaseLockedError):
            guard_hatchery(cohort)


class TestFixationRecovery:
    """固着注入 → FIXED検知 → ノイズ増加 → STABLE自動復旧(請求項4,7)。"""

    async def test_full_recovery_loop(self) -> None:
        cohort = make_cohort()

        # (1) 健全な初期状態: 散逸度は下限以上
        r = await run_cycle(cohort, cycle_cfg())
        assert r.dissipation > TH.lower

        # (2) 固着注入: 全エージェントを同一挙動に強制
        fixed_vec = cohort.teacher_vector.copy()
        for s in cohort.slots:
            s.adapter.force_behavior(fixed_vec)  # type: ignore[attr-defined]

        # (3) h=2サイクルでFIXED確定 → ノイズ注入開始
        await run_cycle(cohort, cycle_cfg())
        r2 = await run_cycle(cohort, cycle_cfg())
        assert r2.dissipation < TH.lower
        assert r2.health == HealthStatus.FIXED
        assert r2.noise_amount > 0.0  # 請求項7: ノイズ付加量の動的変更

        # (4) ノイズにより挙動が拡散 → STABLEへ復帰
        recovered = False
        for _ in range(30):
            r = await run_cycle(cohort, cycle_cfg())
            if r.health == HealthStatus.STABLE:
                recovered = True
                break
        assert recovered, "群がSTABLEに自動復旧しなかった"
        assert r.dissipation > TH.lower

    async def test_dynamics_relaxes_after_recovery(self) -> None:
        """STABLE復帰後はノイズが基準値へ緩やかに回帰する。"""
        cohort = make_cohort()
        for s in cohort.slots:
            s.adapter.force_behavior(cohort.teacher_vector)  # type: ignore[attr-defined]
        peak = 0.0
        last = None
        for _ in range(40):
            last = await run_cycle(cohort, cycle_cfg())
            peak = max(peak, last.noise_amount)
            if last.health == HealthStatus.STABLE:
                break
        assert last is not None and last.health == HealthStatus.STABLE
        for _ in range(5):
            last = await run_cycle(cohort, cycle_cfg())
        assert last.noise_amount < peak  # 回帰(relax)している


class TestRehatchInPlace:
    """逸脱スロットの非破壊的再初期化(請求項1,5,6)。"""

    async def test_deviant_slot_rehatched_with_identity_preserved(self) -> None:
        cohort = make_cohort()
        await run_cycle(cohort, cycle_cfg())

        # スロット003を教師ベクトルの逆方向へ逸脱させる
        deviant = cohort.slots[2]
        deviant.adapter.force_behavior(-cohort.teacher_vector)  # type: ignore[attr-defined]
        original_slot_id = deviant.slot_id
        events_before = len(deviant.events)

        # 平滑化(F̂=0.5·new+0.5·prev)を経て閾値を割るまで回す
        rehatched = None
        for _ in range(5):
            r = await run_cycle(cohort, cycle_cfg())
            hits = [o for o in r.rehatched if o.slot_id == original_slot_id]
            if hits:
                rehatched = hits[0]
                break

        assert rehatched is not None, "逸脱スロットがRehatch選定されなかった"
        assert rehatched.reason == str(RehatchReason.LOW_FITNESS)
        assert rehatched.committed

        # ★請求項1の核: slot_id・表示ID・履歴の連続性が維持され、世代のみ+1
        assert deviant.slot_id == original_slot_id
        assert deviant.generation == 1
        assert len(deviant.events) > events_before  # 履歴は途切れず追記
        assert deviant.maturity == 0  # 全面再配置で成熟度リセット

        # 復旧後は教師ベクトル方向に再適合している(請求項6: TV基づく初期値)
        assert deviant.fitness_hat is not None and deviant.fitness_hat >= 0.5

    async def test_lineage_chain_verifiable_after_rehatch(self) -> None:
        """監査要件: Rehatch後も全履歴がハッシュチェーンで検証・再生可能。"""
        cohort = make_cohort()
        await run_cycle(cohort, cycle_cfg())
        deviant = cohort.slots[0]
        deviant.adapter.force_behavior(-cohort.teacher_vector)  # type: ignore[attr-defined]
        for _ in range(5):
            await run_cycle(cohort, cycle_cfg())

        verify_chain(deviant.events)  # 改竄なし
        state = replay_slot(deviant.events)
        assert state.slot_id == deviant.slot_id
        assert state.generation == deviant.generation  # リプレイと投影が一致
        assert state.event_count == len(deviant.events)


class TestDryRun:
    async def test_dry_run_decides_but_does_not_actuate(self) -> None:
        """dry-run: 判断のみで作用しない(FR-LC-03)。"""
        cohort = make_cohort()
        await run_cycle(cohort, cycle_cfg())
        deviant = cohort.slots[0]
        deviant.adapter.force_behavior(-cohort.teacher_vector)  # type: ignore[attr-defined]

        for _ in range(5):
            r = await run_cycle(cohort, cycle_cfg(dry_run=True))
        assert r.rehatched == []
        assert deviant.generation == 0  # 作用していない


class TestDeterminism:
    async def test_same_seed_same_trajectory(self) -> None:
        """監査リプレイ: 同一シード・同一操作列 → 同一の指標軌跡。"""
        async def trajectory() -> list[float]:
            cohort = make_cohort()
            out = []
            for _ in range(5):
                r = await run_cycle(cohort, cycle_cfg())
                out.append(r.dissipation)
            return out

        assert await trajectory() == pytest.approx(await trajectory())
