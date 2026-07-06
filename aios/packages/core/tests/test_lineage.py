from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from aios_core.lineage.events import GENESIS_HASH, EventChainBuilder, SlotEventType
from aios_core.lineage.replay import ChainVerificationError, replay_slot, verify_chain
from aios_core.types import SlotStatus

T0 = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)


def build_chain() -> tuple[EventChainBuilder, list]:
    b = EventChainBuilder(slot_id="slot-001")
    t = [T0 + timedelta(minutes=i) for i in range(6)]
    events = [
        b.append(SlotEventType.SLOT_CREATED, 0, {"seed": "t0"}, t[0]),
        b.append(SlotEventType.TASK_COMPLETED, 0, {"maturity_delta": 10}, t[1]),
        b.append(SlotEventType.TASK_COMPLETED, 0, {"maturity_delta": 5}, t[2]),
        b.append(SlotEventType.REHATCH_STARTED, 0, {"reason": "LOW_FITNESS"}, t[3]),
        b.append(
            SlotEventType.REHATCH_COMPLETED,
            0,
            {"strategy": "prompt_recompose", "maturity_after": 0, "tv_id": "tv-42"},
            T0 + timedelta(minutes=4),
        ),
        b.append(SlotEventType.TASK_COMPLETED, 1, {"maturity_delta": 3}, T0 + timedelta(minutes=5)),
    ]
    return b, events


class TestHashChain:
    def test_chain_verifies(self) -> None:
        _, events = build_chain()
        verify_chain(events)  # 例外なし
        assert events[0].prev_hash == GENESIS_HASH

    def test_tampered_payload_detected(self) -> None:
        """改竄検知(FR-CH-02): payloadを書き換えるとhashが合わない。"""
        _, events = build_chain()
        events[1] = replace(events[1], payload={"maturity_delta": 9999})
        with pytest.raises(ChainVerificationError) as ei:
            verify_chain(events)
        assert ei.value.index == 1

    def test_reordered_events_detected(self) -> None:
        _, events = build_chain()
        events[1], events[2] = events[2], events[1]
        with pytest.raises(ChainVerificationError):
            verify_chain(events)

    def test_deleted_event_detected(self) -> None:
        """途中イベントの削除(履歴の断絶)も検知される。"""
        _, events = build_chain()
        del events[2]
        with pytest.raises(ChainVerificationError):
            verify_chain(events)


class TestReplay:
    def test_replay_reconstructs_state(self) -> None:
        """イベント再生で世代・状態・成熟度が復元できる(投影再構築)。"""
        _, events = build_chain()
        state = replay_slot(events)
        assert state.slot_id == "slot-001"
        assert state.generation == 1  # REHATCH_COMPLETEDで+1
        assert state.status == SlotStatus.ACTIVE
        assert state.maturity == 3  # Rehatchでリセット後、+3

    def test_identity_survives_rehatch(self) -> None:
        """請求項1の核: Rehatch後もslot_idと履歴の連続性が維持される。"""
        _, events = build_chain()
        state = replay_slot(events)
        assert state.event_count == 6  # Rehatch前の履歴も途切れず数えられる
        assert {e.slot_id for e in events} == {"slot-001"}

    def test_rollback_keeps_generation(self) -> None:
        b = EventChainBuilder(slot_id="s")
        events = [
            b.append(SlotEventType.SLOT_CREATED, 0, {}, T0),
            b.append(SlotEventType.REHATCH_STARTED, 0, {}, T0 + timedelta(minutes=1)),
            b.append(
                SlotEventType.REHATCH_ROLLED_BACK,
                0,
                {"error": "smoke_failed"},
                T0 + timedelta(minutes=2),
            ),
        ]
        state = replay_slot(events)
        assert state.generation == 0  # ロールバックは世代据え置き
        assert state.status == SlotStatus.ACTIVE

    def test_quarantine_flow(self) -> None:
        b = EventChainBuilder(slot_id="s")
        events = [
            b.append(SlotEventType.SLOT_CREATED, 0, {}, T0),
            b.append(
                SlotEventType.QUARANTINED,
                0,
                {"centroid": "prompt_injection"},
                T0 + timedelta(minutes=1),
            ),
        ]
        assert replay_slot(events).status == SlotStatus.QUARANTINED

    def test_first_event_must_be_creation(self) -> None:
        b = EventChainBuilder(slot_id="s")
        events = [b.append(SlotEventType.TASK_COMPLETED, 0, {}, T0)]
        with pytest.raises(ValueError):
            replay_slot(events)
