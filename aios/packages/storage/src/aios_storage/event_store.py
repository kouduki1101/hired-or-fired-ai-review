"""追記専用イベントストア(FR-CH-02 / docs/04 §2.3, 不変条件2)。

挿入時にスロット単位のハッシュチェーン連続性を検証する:
    event.prev_hash == 直前イベントの hash(初回は GENESIS_HASH)
UPDATE / DELETE のメソッドは提供しない(No-Delete by Design)。
"""

from __future__ import annotations

from datetime import UTC, datetime

from aios_core.lineage.events import GENESIS_HASH, SlotEvent, SlotEventType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aios_storage.models import SlotEventRow


def _as_utc(dt: datetime) -> datetime:
    """SQLite等tz情報を持たない方言はUTC naiveで返すため復元する(ハッシュ整合)。"""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


class ChainMismatchError(Exception):
    """チェーン不整合(並行書込み・改竄・欠落)。"""


class EventStore:
    """スロット運用履歴の永続化。読み書きのみ(削除・更新なし)。"""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def last_hash(self, slot_id: str) -> bytes:
        row = await self._session.scalar(
            select(SlotEventRow)
            .where(SlotEventRow.slot_id == slot_id)
            .order_by(SlotEventRow.event_id.desc())
            .limit(1)
        )
        return row.hash if row is not None else GENESIS_HASH

    async def append(self, event: SlotEvent, *, cohort_id: str, cycle_id: str | None = None) -> int:
        """チェーン検証付き追記。不整合は ChainMismatchError。"""
        if not event.verify():
            raise ChainMismatchError("event hash does not match its body")
        expected = await self.last_hash(event.slot_id)
        if event.prev_hash != expected:
            raise ChainMismatchError(
                f"prev_hash mismatch for slot {event.slot_id}: "
                f"expected {expected.hex()[:12]}, got {event.prev_hash.hex()[:12]}"
            )
        row = SlotEventRow(
            tenant_id=self._tenant_id,
            slot_id=event.slot_id,
            cohort_id=cohort_id,
            cycle_id=cycle_id,
            event_type=str(event.event_type),
            generation=event.generation,
            payload=event.payload,
            prev_hash=event.prev_hash,
            hash=event.hash,
            occurred_at=event.occurred_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row.event_id

    async def list_for_slot(self, slot_id: str) -> list[SlotEvent]:
        """時系列順の全イベント(core型に復元。リプレイ・監査エクスポート用)。"""
        rows = (
            await self._session.scalars(
                select(SlotEventRow)
                .where(SlotEventRow.slot_id == slot_id)
                .order_by(SlotEventRow.event_id.asc())
            )
        ).all()
        return [
            SlotEvent(
                slot_id=r.slot_id,
                event_type=SlotEventType(r.event_type),
                generation=r.generation,
                payload=r.payload,
                occurred_at=_as_utc(r.occurred_at),
                prev_hash=r.prev_hash,
                hash=r.hash,
            )
            for r in rows
        ]
