"""運用履歴イベント(請求項1: 識別情報+運用履歴の記憶 / FR-CH-02)。

追記専用・ハッシュチェーンによる改竄検知。
    hash = SHA-256( prev_hash || canonical_json(event_body) )
同一 slot_id 内で prev_hash が直前イベントの hash に一致することを不変条件とする。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

GENESIS_HASH = b"\x00" * 32  # スロット最初のイベントの prev_hash


class SlotEventType(StrEnum):
    SLOT_CREATED = "SLOT_CREATED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TRAINING_STEP = "TRAINING_STEP"
    REHATCH_SELECTED = "REHATCH_SELECTED"
    REHATCH_STARTED = "REHATCH_STARTED"
    REHATCH_COMPLETED = "REHATCH_COMPLETED"
    REHATCH_ROLLED_BACK = "REHATCH_ROLLED_BACK"
    STATUS_CHANGED = "STATUS_CHANGED"
    DYNAMICS_APPLIED = "DYNAMICS_APPLIED"
    QUARANTINED = "QUARANTINED"
    RESTORED = "RESTORED"
    PROPOSAL_SUBMITTED = "PROPOSAL_SUBMITTED"
    PROPOSAL_DECIDED = "PROPOSAL_DECIDED"
    CONFIG_CHANGED = "CONFIG_CHANGED"


# 世代を変化させうるイベント(docs/04 不変条件3)
GENERATION_CHANGING = {SlotEventType.REHATCH_COMPLETED, SlotEventType.REHATCH_ROLLED_BACK}


def _canonical_body(
    slot_id: str,
    event_type: SlotEventType,
    generation: int,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> bytes:
    """ハッシュ対象の正規化表現(キー順固定・区切り固定・ISO8601)。"""
    body = {
        "slot_id": slot_id,
        "event_type": str(event_type),
        "generation": generation,
        "payload": payload,
        "occurred_at": occurred_at.isoformat(),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def compute_hash(
    prev_hash: bytes,
    slot_id: str,
    event_type: SlotEventType,
    generation: int,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> bytes:
    return hashlib.sha256(
        prev_hash + _canonical_body(slot_id, event_type, generation, payload, occurred_at)
    ).digest()


@dataclass(frozen=True)
class SlotEvent:
    slot_id: str
    event_type: SlotEventType
    generation: int  # 発生時点の世代
    payload: dict[str, Any]
    occurred_at: datetime
    prev_hash: bytes
    hash: bytes

    @classmethod
    def create(
        cls,
        *,
        slot_id: str,
        event_type: SlotEventType,
        generation: int,
        payload: dict[str, Any],
        occurred_at: datetime,
        prev_hash: bytes,
    ) -> SlotEvent:
        """prev_hash からチェーンを繋いだイベントを生成する。"""
        if generation < 0:
            raise ValueError("generation must be non-negative")
        return cls(
            slot_id=slot_id,
            event_type=event_type,
            generation=generation,
            payload=payload,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
            hash=compute_hash(prev_hash, slot_id, event_type, generation, payload, occurred_at),
        )

    def verify(self) -> bool:
        """自身のハッシュが本文と整合しているか。"""
        return self.hash == compute_hash(
            self.prev_hash,
            self.slot_id,
            self.event_type,
            self.generation,
            self.payload,
            self.occurred_at,
        )


@dataclass
class EventChainBuilder:
    """スロット単位でチェーンを構築するヘルパ(テスト・アプリ層用)。"""

    slot_id: str
    last_hash: bytes = field(default=GENESIS_HASH)

    def append(
        self,
        event_type: SlotEventType,
        generation: int,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> SlotEvent:
        ev = SlotEvent.create(
            slot_id=self.slot_id,
            event_type=event_type,
            generation=generation,
            payload=payload,
            occurred_at=occurred_at,
            prev_hash=self.last_hash,
        )
        self.last_hash = ev.hash
        return ev
