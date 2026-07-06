"""次元拡張スケーリング(請求項9 / 図5)のe2e。"""

from __future__ import annotations

import numpy as np
import pytest
from aios_adapters.fake import FakeAgentAdapter
from aios_core.lineage.events import SlotEventType
from aios_core.policy.safety import NegativeCentroid
from aios_core.types import HealthThresholds
from aios_orchestrator.cycle import run_cycle
from aios_orchestrator.runtime import CohortRuntime, hatch_cohort
from aios_orchestrator.scaling import expand_cohort_dimension

DIM = 8
TH = HealthThresholds(lower=0.05, upper=1.2)


def make_cohort() -> CohortRuntime:
    return hatch_cohort(
        adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=i),
        slot_count=6,
        initial_tv=np.random.default_rng(3).normal(size=DIM),
        thresholds=TH,
        seed=4,
    )


class TestExpandDimension:
    async def test_expand_preserves_population_and_extends_tv(self) -> None:
        """請求項9: スロット数を維持したまま第1の指標の次元数を拡張する。"""
        cohort = make_cohort()
        await run_cycle(cohort)
        slot_ids_before = [s.slot_id for s in cohort.slots]

        new_dim = await expand_cohort_dimension(
            cohort, 4, ["倫理的配慮", "法務知識", "創造性", "簡潔さ"]
        )
        assert new_dim == DIM + 4
        assert cohort.teacher_vector.shape == (DIM + 4,)
        assert [s.slot_id for s in cohort.slots] == slot_ids_before  # K不変
        assert cohort.value_axes == {
            8: "倫理的配慮", 9: "法務知識", 10: "創造性", 11: "簡潔さ",
        }

    async def test_slots_realigned_and_cycle_continues(self) -> None:
        """拡張後も無停止で制御サイクルが回る(入力次元整合、¶0097)。"""
        cohort = make_cohort()
        await run_cycle(cohort)
        await expand_cohort_dimension(cohort, 2, ["a", "b"])

        r = await run_cycle(cohort)  # 全スロットの状態がN+M次元で観測される
        assert r.dissipation == r.dissipation  # not NaN
        assert r.probe_missing == 0
        for s in cohort.slots:
            state = await s.adapter.get_state([])
            assert state.shape == (DIM + 2,)
            assert any(
                e.event_type == SlotEventType.CONFIG_CHANGED
                and e.payload.get("change") == "dimension_expanded"
                for e in s.events
            )

    async def test_negative_centroids_padded(self) -> None:
        """禁止ベクトルも同一空間へパディングされ安全監視が継続する。"""
        cohort = make_cohort()
        cohort.negative_centroids.append(
            NegativeCentroid(label="bad", vector=tuple(np.eye(DIM)[0]), threshold=0.9)
        )
        await expand_cohort_dimension(cohort, 3, ["x", "y", "z"])
        assert len(cohort.negative_centroids[0].vector) == DIM + 3
        await run_cycle(cohort)  # 照合が次元不一致で落ちない

    async def test_labels_required_for_every_dim(self) -> None:
        cohort = make_cohort()
        with pytest.raises(ValueError):
            await expand_cohort_dimension(cohort, 3, ["only-one"])

    async def test_shrink_forbidden(self) -> None:
        cohort = make_cohort()
        with pytest.raises(ValueError):
            await expand_cohort_dimension(cohort, 0, [])

    async def test_new_axis_variance_grows_under_noise(self) -> None:
        """¶0098: ノイズ探索により新価値軸方向の分散が拡大していく。"""
        cohort = make_cohort()
        await expand_cohort_dimension(cohort, 2, ["axis1", "axis2"])
        for s in cohort.slots:
            await s.adapter.apply_dynamics(cohort.dynamics.__class__(noise_amount=0.2))
        for _ in range(5):
            await run_cycle(cohort)
        states = np.stack([await s.adapter.get_state([]) for s in cohort.slots])
        assert float(states[:, DIM:].var()) > 0.0  # 新次元が探索されている
