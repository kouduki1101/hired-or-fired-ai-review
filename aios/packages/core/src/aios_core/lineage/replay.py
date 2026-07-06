"""イベント再生(FR-GV-01〜02 / docs/03 §1.1 イベントソーシング)。

- verify_chain: ハッシュチェーンの完全性検証(改竄検知)
- replay_slot: イベント列からスロットの現在状態(世代・状態・成熟度)を復元。
  投影(slotsテーブル)の再構築、および監査時の「当時状態」復元に使う。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aios_core.lineage.events import GENESIS_HASH, SlotEvent, SlotEventType
from aios_core.types import SlotStatus


class ChainVerificationError(Exception):
    def __init__(self, index: int, message: str) -> None:
        super().__init__(f"event[{index}]: {message}")
        self.index = index


def verify_chain(events: list[SlotEvent]) -> None:
    """slot_id単位・時系列順のイベント列を検証する。失敗時は例外。"""
    prev = GENESIS_HASH
    slot_ids = {e.slot_id for e in events}
    if len(slot_ids) > 1:
        raise ValueError(f"events must belong to a single slot, got {slot_ids}")
    for i, ev in enumerate(events):
        if ev.prev_hash != prev:
            raise ChainVerificationError(i, "prev_hash does not match previous event hash")
        if not ev.verify():
            raise ChainVerificationError(i, "hash does not match event body (tampered)")
        prev = ev.hash


@dataclass(frozen=True)
class ReplayedSlotState:
    slot_id: str
    generation: int
    status: SlotStatus
    maturity: int
    event_count: int
    last_event_at: datetime | None


def replay_slot(events: list[SlotEvent], *, verify: bool = True) -> ReplayedSlotState:
    """イベント列からスロット状態を復元する。

    世代は REHATCH_COMPLETED でのみ+1(ROLLED_BACKは据え置き: 旧世代構成へ復帰)。
    成熟度は TASK_COMPLETED / TRAINING_STEP の payload["maturity_delta"] を加算し、
    REHATCH_COMPLETED の payload["maturity_after"] で置換(全面=0、部分=減算後値)。
    """
    if not events:
        raise ValueError("cannot replay empty event list")
    if verify:
        verify_chain(events)

    first = events[0]
    if first.event_type != SlotEventType.SLOT_CREATED:
        raise ValueError("first event must be SLOT_CREATED")

    generation = 0
    status = SlotStatus.ACTIVE
    maturity = 0

    for ev in events:
        et = ev.event_type
        if et == SlotEventType.SLOT_CREATED:
            generation = 0
            status = SlotStatus.ACTIVE
            maturity = 0
        elif et in (SlotEventType.TASK_COMPLETED, SlotEventType.TRAINING_STEP):
            maturity += int(ev.payload.get("maturity_delta", 1))
        elif et == SlotEventType.REHATCH_STARTED:
            status = SlotStatus.REHATCHING
        elif et == SlotEventType.REHATCH_COMPLETED:
            generation += 1
            maturity = int(ev.payload.get("maturity_after", 0))
            status = SlotStatus.ACTIVE
        elif et == SlotEventType.REHATCH_ROLLED_BACK:
            status = SlotStatus.ACTIVE  # 世代は据え置き(直前世代の構成へ復帰)
        elif et == SlotEventType.QUARANTINED:
            status = SlotStatus.QUARANTINED
        elif et == SlotEventType.RESTORED:
            status = SlotStatus.ACTIVE
        elif et == SlotEventType.STATUS_CHANGED:
            status = SlotStatus(ev.payload["to"])

    return ReplayedSlotState(
        slot_id=first.slot_id,
        generation=generation,
        status=status,
        maturity=maturity,
        event_count=len(events),
        last_event_at=events[-1].occurred_at,
    )
