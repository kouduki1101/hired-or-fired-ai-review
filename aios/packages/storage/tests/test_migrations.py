"""Alembicマイグレーションの検証(NFR-OP-05)。

- upgrade head がモデル(Base.metadata)と乖離しないこと(ドリフトゼロ)
- マイグレーション適用後のDBでイベントストアが動作すること
- PostgreSQL結合は AIOS_PG_TEST_URL 設定時のみ実行(CI/compose環境用)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from aios_core.lineage.events import EventChainBuilder, SlotEventType
from aios_storage.event_store import EventStore
from aios_storage.models import Base, CohortRow, SlotRow
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

STORAGE_DIR = Path(__file__).resolve().parents[1]


def _alembic_config(sync_url: str) -> Config:
    cfg = Config(str(STORAGE_DIR / "alembic.ini"))
    os.environ["AIOS_ALEMBIC_URL"] = sync_url
    return cfg


def _upgrade_and_check_drift(sync_url: str) -> None:
    command.upgrade(_alembic_config(sync_url), "head")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            diff = compare_metadata(context, Base.metadata)
            assert diff == [], f"migration drift detected: {diff}"
        assert "alembic_version" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


class TestSqliteMigration:
    def test_upgrade_head_matches_models(self, tmp_path: Path) -> None:
        """ドリフトゼロ: upgrade後のスキーマがBase.metadataと完全一致する。"""
        _upgrade_and_check_drift(f"sqlite:///{tmp_path}/mig.db")

    async def test_event_store_works_on_migrated_db(self, tmp_path: Path) -> None:
        """マイグレーション適用済みDB上でチェーン付き追記・読出しが動く。"""
        db = f"{tmp_path}/mig2.db"
        command.upgrade(_alembic_config(f"sqlite:///{db}"), "head")

        engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                now = datetime(2026, 7, 6, tzinfo=UTC)
                session.add(
                    CohortRow(
                        cohort_id="c1", tenant_id="t1", name="m", phase="OPERATING",
                        slot_count=2, created_at=now,
                    )
                )
                session.add(
                    SlotRow(
                        slot_id="s1", tenant_id="t1", cohort_id="c1",
                        display_id="001", adapter_kind="fake_agent",
                    )
                )
                await session.flush()

                store = EventStore(session, tenant_id="t1")
                builder = EventChainBuilder(slot_id="s1")
                ev = builder.append(SlotEventType.SLOT_CREATED, 0, {}, now)
                await store.append(ev, cohort_id="c1")
                loaded = await store.list_for_slot("s1")
                assert len(loaded) == 1 and loaded[0].verify()
        finally:
            await engine.dispose()


@pytest.mark.skipif(
    not os.environ.get("AIOS_PG_TEST_URL"),
    reason="PostgreSQL結合はAIOS_PG_TEST_URL設定時のみ(例: compose環境のCI)",
)
class TestPostgresMigration:
    def test_upgrade_head_on_postgres(self) -> None:
        _upgrade_and_check_drift(os.environ["AIOS_PG_TEST_URL"])
