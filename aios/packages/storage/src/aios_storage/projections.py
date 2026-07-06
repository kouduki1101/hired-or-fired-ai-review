"""投影の再構築(docs/03 §1.1: slotsテーブルはイベントの導出物)。

イベント再生(aios_core.lineage.replay)の結果でSlotRowを更新する。
スキーマ変更・障害復旧時に「正=イベント」から投影を作り直せることを保証する。
"""

from __future__ import annotations

from aios_core.lineage.replay import ReplayedSlotState, replay_slot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aios_storage.event_store import EventStore
from aios_storage.models import SlotRow


async def rebuild_slot_projection(
    session: AsyncSession, store: EventStore, slot_id: str
) -> ReplayedSlotState:
    """イベントからスロット投影を再構築し、SlotRowへ反映する。"""
    events = await store.list_for_slot(slot_id)
    state = replay_slot(events)  # チェーン検証込み

    row = await session.scalar(select(SlotRow).where(SlotRow.slot_id == slot_id))
    if row is None:
        raise LookupError(f"slot {slot_id} not found in projection table")
    row.generation = state.generation
    row.status = str(state.status)
    row.maturity = state.maturity
    await session.flush()
    return state
