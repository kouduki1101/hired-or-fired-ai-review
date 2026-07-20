"""アーカイブ継承の e2e: Rehatch → 退役世代がアーカイブ → 次の Rehatch が継承。"""

from __future__ import annotations

import numpy as np
from aios_adapters.fake import FakeAgentAdapter
from aios_core.lineage.events import SlotEventType
from aios_core.types import HealthThresholds
from aios_orchestrator.cycle import rehatch_slot
from aios_orchestrator.runtime import CohortRuntime, hatch_cohort

DIM = 8
TH = HealthThresholds(lower=0.05, upper=1.2, hysteresis_cycles=2)


def _cohort() -> CohortRuntime:
    rng = np.random.default_rng(21)
    return hatch_cohort(
        adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=500 + i),
        slot_count=3,
        initial_tv=rng.normal(size=DIM),
        thresholds=TH,
        diversity=0.4,
        seed=17,
    )


class TestArchiveOnRehatch:
    async def test_committed_rehatch_archives_retired_generation(self) -> None:
        cohort = _cohort()
        slot = cohort.slots[0]
        slot.fitness_hat = 0.8  # 退役時の成績として記録されるはず
        assert cohort.archives == []

        outcome = await rehatch_slot(cohort, slot.slot_id, "LOW_FITNESS")
        assert outcome.committed is True
        assert len(cohort.archives) == 1
        entry = cohort.archives[0]
        assert entry.source_slot_id == slot.slot_id
        assert entry.source_generation == 0  # 退役したのは第0世代
        assert entry.best_score == 0.8
        assert entry.config["context_vector"] is not None  # 広義の内部パラメータを保存

        completed = [
            e for e in slot.events if e.event_type == SlotEventType.REHATCH_COMPLETED
        ]
        assert completed[-1].payload["archived_as"] == entry.archive_id
        assert completed[-1].payload["inherited_from"] is None  # 初回は継承元なし

    async def test_second_rehatch_inherits_from_best_archive(self) -> None:
        cohort = _cohort()
        first = cohort.slots[0]
        first.fitness_hat = 0.9
        # 退役構成に識別可能な system_prompt を持たせておく
        await first.adapter.apply_params(
            type(await first.adapter.snapshot())(system_prompt="veteran-knowledge")
        )
        await rehatch_slot(cohort, first.slot_id, "LOW_FITNESS")
        assert cohort.archives[0].config["system_prompt"] == "veteran-knowledge"

        # 別スロットの Rehatch は蓄積済みアーカイブを継承する
        second = cohort.slots[1]
        await rehatch_slot(cohort, second.slot_id, "LOW_FITNESS")
        completed = [
            e for e in second.events if e.event_type == SlotEventType.REHATCH_COMPLETED
        ]
        assert completed[-1].payload["inherited_from"] == cohort.archives[0].archive_id
        # 継承された system_prompt が新構成に反映されている
        snap = await second.adapter.snapshot()
        assert snap.system_prompt == "veteran-knowledge"
        # 2件目のアーカイブも追加されている(累積)
        assert len(cohort.archives) == 2
