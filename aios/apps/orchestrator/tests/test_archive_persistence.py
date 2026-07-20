"""知識アーカイブの永続化ラウンドトリップ(docs/06 §7 + docs/04 正規形)。"""

from __future__ import annotations

import numpy as np
import pytest
from aios_adapters.fake import FakeAgentAdapter
from aios_adapters.spi import ModelConfig
from aios_core.types import HealthThresholds
from aios_orchestrator.cycle import rehatch_slot
from aios_orchestrator.persistence import load_cohort, save_cohort
from aios_orchestrator.runtime import hatch_cohort
from aios_storage.models import KnowledgeArchiveRow, TeacherVectorRow
from aios_storage.schema import create_all
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DIM = 8
TH = HealthThresholds(lower=0.05, upper=1.2, hysteresis_cycles=2)


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


def restore_adapter(index: int, config: ModelConfig) -> FakeAgentAdapter:
    assert config.context_vector is not None
    return FakeAgentAdapter(behavior=np.asarray(config.context_vector), seed=700 + index)


async def test_archives_survive_restart(session: AsyncSession) -> None:
    rng = np.random.default_rng(31)
    cohort = hatch_cohort(
        adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=700 + i),
        slot_count=3,
        initial_tv=rng.normal(size=DIM),
        thresholds=TH,
        seed=13,
    )
    slot = cohort.slots[0]
    slot.fitness_hat = 0.75
    await rehatch_slot(cohort, slot.slot_id, "LOW_FITNESS")
    assert len(cohort.archives) == 1
    original = cohort.archives[0]

    await save_cohort(session, cohort)
    # 冪等: 二重保存してもアーカイブは増えない(append-only + archive_id で重複回避)
    await save_cohort(session, cohort)
    rows = (await session.scalars(select(KnowledgeArchiveRow))).all()
    assert len(rows) == 1
    assert rows[0].kind == "rehatch_retired"
    # TVは teacher_vectors に source="archive" で正規保存され参照される
    tv_row = await session.get(TeacherVectorRow, rows[0].tv_id)
    assert tv_row is not None and tv_row.source == "archive"

    # 「再起動」後もアーカイブが継承候補として復元される
    restored = await load_cohort(session, cohort.cohort_id, restore_adapter)
    assert len(restored.archives) == 1
    entry = restored.archives[0]
    assert entry.archive_id == original.archive_id
    assert entry.best_score == original.best_score
    assert entry.source_slot_id == original.source_slot_id
    assert entry.tv == pytest.approx(original.tv)
    assert entry.config.get("context_vector") is not None

    # 復元後の Rehatch が復元済みアーカイブを継承できる(実運用の続き)
    second = restored.slots[1]
    outcome = await rehatch_slot(restored, second.slot_id, "LOW_FITNESS")
    assert outcome.committed is True
    from aios_core.lineage.events import SlotEventType

    completed = [e for e in second.events if e.event_type == SlotEventType.REHATCH_COMPLETED]
    assert completed[-1].payload["inherited_from"] == original.archive_id
