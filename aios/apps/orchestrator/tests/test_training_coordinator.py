"""学習系 Rehatch 調停(TrainingCoordinator)の e2e。

非同期ジョブ(FakeTrainer)を投入→進捗→完了させ、完了時に Rehatch-in-Place
(slot_id・履歴維持で世代+1)が起きることと、失敗時にロールバックされることを検証。
"""

from __future__ import annotations

import numpy as np
from aios_adapters.fake import FakeAgentAdapter
from aios_adapters.spi import RehatchStrategy
from aios_adapters.training_fake import FakeTrainer
from aios_core.lineage.events import SlotEventType
from aios_core.lineage.replay import verify_chain
from aios_core.types import HealthThresholds, SlotStatus
from aios_orchestrator.runtime import CohortRuntime, hatch_cohort
from aios_orchestrator.training import TrainingCoordinator

DIM = 8
TH = HealthThresholds(lower=0.05, upper=1.2, hysteresis_cycles=2)


def _cohort() -> CohortRuntime:
    rng = np.random.default_rng(3)
    return hatch_cohort(
        adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=200 + i),
        slot_count=3,
        initial_tv=rng.normal(size=DIM),
        thresholds=TH,
        diversity=0.4,
        seed=11,
    )


def _now():
    from datetime import UTC, datetime

    return datetime(2026, 7, 7, tzinfo=UTC)


class TestLearningRehatch:
    async def test_submit_keeps_slot_active(self) -> None:
        cohort = _cohort()
        slot = cohort.slots[0]
        coord = TrainingCoordinator(FakeTrainer())
        job_id = await coord.submit(
            slot, RehatchStrategy.DISTILLATION, cohort.teacher_vector, _now()
        )
        # 学習中もスロットはタスクを処理できる(オフラインにしない)
        assert slot.status == SlotStatus.ACTIVE
        assert coord.active_job(slot.slot_id) == job_id

    async def test_success_triggers_rehatch_in_place(self) -> None:
        cohort = _cohort()
        slot = cohort.slots[0]
        original_id = slot.slot_id
        gen0 = slot.generation
        events0 = len(slot.events)

        coord = TrainingCoordinator(FakeTrainer())
        job_id = await coord.submit(
            slot, RehatchStrategy.DISTILLATION, cohort.teacher_vector, _now(), max_steps=3
        )
        # 未完了の間は None
        assert await coord.apply_if_ready(slot, job_id, cohort.teacher_vector, _now()) is None
        assert await coord.apply_if_ready(slot, job_id, cohort.teacher_vector, _now()) is None
        # 3回目で完了 → Rehatch-in-Place
        outcome = await coord.apply_if_ready(slot, job_id, cohort.teacher_vector, _now())
        assert outcome is not None and outcome.committed is True
        assert outcome.new_generation == gen0 + 1
        # ID・履歴は維持(Rehatch-in-Place の核心)
        assert slot.slot_id == original_id
        assert slot.generation == gen0 + 1
        assert slot.maturity == 0
        assert len(slot.events) > events0
        assert coord.active_job(slot.slot_id) is None
        # 監査連鎖は健全なまま、蒸留戦略で完了記録
        verify_chain(slot.events)  # 改竄なし(失敗時は例外)
        completed = [e for e in slot.events if e.event_type == SlotEventType.REHATCH_COMPLETED]
        assert completed and completed[-1].payload["strategy"] == "distillation"
        assert completed[-1].payload["reason"] == "learning"

    async def test_failure_rolls_back(self) -> None:
        cohort = _cohort()
        slot = cohort.slots[1]
        gen0 = slot.generation
        trainer = FakeTrainer()
        trainer.inject_failure(slot.slot_id, at_step=2)
        coord = TrainingCoordinator(trainer)
        job_id = await coord.submit(
            slot, RehatchStrategy.DISTILLATION, cohort.teacher_vector, _now(), max_steps=5
        )
        assert await coord.apply_if_ready(slot, job_id, cohort.teacher_vector, _now()) is None
        outcome = await coord.apply_if_ready(slot, job_id, cohort.teacher_vector, _now())
        assert outcome is not None and outcome.committed is False
        # 世代据え置き・スロットは復帰
        assert slot.generation == gen0
        assert slot.status == SlotStatus.ACTIVE
        verify_chain(slot.events)  # 改竄なし(失敗時は例外)
        assert any(e.event_type == SlotEventType.REHATCH_ROLLED_BACK for e in slot.events)
