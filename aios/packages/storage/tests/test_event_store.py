"""イベントストアの永続化テスト(SQLite in-memory)。

本番はPostgreSQL+pgvectorだが、チェーン検証・投影再構築のロジックは
方言非依存であり、ここではSQLiteで回帰する(PostgreSQL結合はtests/integrationでP2)。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from aios_core.lineage.events import EventChainBuilder, SlotEventType
from aios_core.types import SlotStatus
from aios_storage.event_store import ChainMismatchError, EventStore
from aios_storage.models import CohortRow, SlotRow
from aios_storage.projections import rebuild_slot_projection
from aios_storage.schema import create_all
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

T0 = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
TENANT = "tenant-1"


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        s.add(
            CohortRow(
                cohort_id="c1",
                tenant_id=TENANT,
                name="test",
                phase="OPERATING",
                slot_count=2,
                created_at=T0,
            )
        )
        s.add(
            SlotRow(
                slot_id="s1",
                tenant_id=TENANT,
                cohort_id="c1",
                display_id="001",
                adapter_kind="fake_agent",
            )
        )
        await s.flush()
        yield s
    await engine.dispose()


def chain_events():
    b = EventChainBuilder(slot_id="s1")
    return [
        b.append(SlotEventType.SLOT_CREATED, 0, {}, T0),
        b.append(SlotEventType.TASK_COMPLETED, 0, {"maturity_delta": 5}, T0 + timedelta(minutes=1)),
        b.append(SlotEventType.REHATCH_STARTED, 0, {}, T0 + timedelta(minutes=2)),
        b.append(
            SlotEventType.REHATCH_COMPLETED,
            0,
            {"maturity_after": 0, "strategy": "tv_init"},
            T0 + timedelta(minutes=3),
        ),
    ]


class TestAppend:
    async def test_roundtrip_preserves_chain(self, session: AsyncSession) -> None:
        store = EventStore(session, tenant_id=TENANT)
        for ev in chain_events():
            await store.append(ev, cohort_id="c1")
        loaded = await store.list_for_slot("s1")
        assert len(loaded) == 4
        assert [e.event_type for e in loaded] == [e.event_type for e in chain_events()]
        # 復元イベントはハッシュ検証を通る
        assert all(e.verify() for e in loaded)

    async def test_rejects_chain_gap(self, session: AsyncSession) -> None:
        """途中を飛ばした追記(履歴の欠落)は拒否される。"""
        store = EventStore(session, tenant_id=TENANT)
        events = chain_events()
        await store.append(events[0], cohort_id="c1")
        with pytest.raises(ChainMismatchError):
            await store.append(events[2], cohort_id="c1")  # events[1]を飛ばす

    async def test_rejects_tampered_event(self, session: AsyncSession) -> None:
        store = EventStore(session, tenant_id=TENANT)
        events = chain_events()
        await store.append(events[0], cohort_id="c1")
        bad = replace(events[1], payload={"maturity_delta": 9999})  # hash不一致
        with pytest.raises(ChainMismatchError):
            await store.append(bad, cohort_id="c1")

    async def test_no_delete_interface(self) -> None:
        """No-Delete by Design: EventStoreに削除・更新の口が存在しない。"""
        methods = {m for m in dir(EventStore) if not m.startswith("_")}
        assert methods == {"append", "last_hash", "list_for_slot"}


class TestProjection:
    async def test_rebuild_from_events(self, session: AsyncSession) -> None:
        """投影(SlotRow)がイベント再生から再構築できる(docs/03 §1.1)。"""
        store = EventStore(session, tenant_id=TENANT)
        for ev in chain_events():
            await store.append(ev, cohort_id="c1")

        state = await rebuild_slot_projection(session, store, "s1")
        assert state.generation == 1
        assert state.status == SlotStatus.ACTIVE

        row = await session.get(SlotRow, "s1")
        assert row is not None
        assert row.generation == 1
        assert row.status == "ACTIVE"
        assert row.maturity == 0  # Rehatchでリセット済み
