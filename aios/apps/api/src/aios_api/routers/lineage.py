"""リネージ照会・開示請求応答(明細書 変形例(4) ¶0224-0227 / FR-GV-01〜03)。

- GET /lineage/tasks/{task_id}: 「なぜAIがその回答をしたのか」への構造化応答。
  担当スロット・世代、当該世代を生成したRehatch(戦略・理由・継承元)、
  適用中だった制御値を特定し、説明文を生成する
- GET /lineage/slots/{slot_id}/history: 運用履歴タイムライン(全世代、チェーン検証付き)
"""

from __future__ import annotations

from typing import Any

from aios_core.lineage.events import SlotEventType
from aios_core.lineage.replay import verify_chain
from fastapi import APIRouter, Response
from pydantic import BaseModel

from aios_api.store import STORE

router = APIRouter(tags=["lineage"])


class GenerationLineage(BaseModel):
    strategy: str | None  # 世代0(卵層生成)はNone
    reason: str | None
    rehatched_at: str | None
    smoke_fitness: float | None


class TaskLineageResponse(BaseModel):
    task_id: str
    handled_by: dict[str, Any]
    generation_lineage: GenerationLineage
    dynamics_at_time: dict[str, float]
    routing: dict[str, str]
    explanation: str


@router.get("/lineage/tasks/{task_id}", response_model=TaskLineageResponse)
async def task_lineage(task_id: str) -> TaskLineageResponse:
    record = STORE.get_task(task_id)
    cohort = STORE.get_cohort(record["cohort_id"])
    slot = next(s for s in cohort.slots if s.slot_id == record["slot_id"])

    # 担当世代を生成したREHATCH_COMPLETEDイベントを特定(世代0は卵層生成)
    gen = record["generation"]
    rehatch_ev = None
    if gen > 0:
        completed = [e for e in slot.events if e.event_type == SlotEventType.REHATCH_COMPLETED]
        if len(completed) >= gen:
            rehatch_ev = completed[gen - 1]  # gen世代目を作ったイベント

    lineage = GenerationLineage(
        strategy=rehatch_ev.payload.get("strategy") if rehatch_ev else None,
        reason=rehatch_ev.payload.get("reason") if rehatch_ev else None,
        rehatched_at=rehatch_ev.occurred_at.isoformat() if rehatch_ev else None,
        smoke_fitness=rehatch_ev.payload.get("smoke_fitness") if rehatch_ev else None,
    )

    if gen == 0:
        origin = "初期化フェーズ(卵層)で生成された第0世代モデル"
    else:
        origin = (
            f"{lineage.rehatched_at}に理由「{lineage.reason}」で"
            f"非破壊的再初期化(戦略: {lineage.strategy})された第{gen}世代モデル"
        )
    explanation = (
        f"本回答はスロット{record['display_id']}の第{gen}世代モデルによるものです。"
        f"同モデルは{origin}であり、割当は「{record['routing_reason']}」の判断で行われました。"
        f"実行時の制御値は学習率補正{record['dynamics']['lr_correction']:.2f}、"
        f"ノイズ量{record['dynamics']['noise_amount']:.2f}です。"
        f"スロットの識別情報と運用履歴は生成以来維持されています。"
    )

    return TaskLineageResponse(
        task_id=task_id,
        handled_by={
            "slot_id": record["slot_id"],
            "display_id": record["display_id"],
            "generation": gen,
            "step_no": record["step_no"],
        },
        generation_lineage=lineage,
        dynamics_at_time=record["dynamics"],
        routing={"cluster": record["cluster"], "reason": record["routing_reason"]},
        explanation=explanation,
    )


@router.get("/lineage/export/{cohort_id}/manifest")
async def export_manifest(cohort_id: str) -> dict[str, Any]:
    """監査エクスポートの完全性マニフェスト(FR-GV-03)。

    スロットごとのイベント数・チェーン末尾ハッシュ・検証結果を返す。
    エクスポート本文(NDJSON)と突き合わせて改竄・欠落を検出できる。
    """
    from datetime import UTC, datetime

    cohort = STORE.get_cohort(cohort_id)
    slots = []
    for slot in cohort.slots:
        verified = True
        try:
            verify_chain(slot.events)
        except Exception:
            verified = False
        slots.append(
            {
                "slot_id": slot.slot_id,
                "display_id": slot.display_id,
                "event_count": len(slot.events),
                "last_hash": slot.events[-1].hash.hex() if slot.events else None,
                "chain_verified": verified,
            }
        )
    return {
        "cohort_id": cohort_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_events": sum(s["event_count"] for s in slots),
        "slots": slots,
    }


@router.get("/lineage/export/{cohort_id}")
async def export_events(cohort_id: str) -> Response:
    """監査エクスポート本文: 全スロットの運用履歴をNDJSONで返す(FR-GV-03)。

    レスポンスヘッダ X-AIOS-Export-SHA256 で本文全体のハッシュを提示する。
    各行に prev_hash/hash を含むため、受領側で単独でチェーン再検証が可能。
    """
    import hashlib
    import json

    cohort = STORE.get_cohort(cohort_id)
    lines: list[str] = []
    for slot in cohort.slots:
        for ev in slot.events:
            lines.append(
                json.dumps(
                    {
                        "slot_id": ev.slot_id,
                        "display_id": slot.display_id,
                        "event_type": str(ev.event_type),
                        "generation": ev.generation,
                        "payload": ev.payload,
                        "occurred_at": ev.occurred_at.isoformat(),
                        "prev_hash": ev.prev_hash.hex(),
                        "hash": ev.hash.hex(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    body = ("\n".join(lines) + "\n").encode() if lines else b""
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={
            "X-AIOS-Export-SHA256": hashlib.sha256(body).hexdigest(),
            "Content-Disposition": f'attachment; filename="aios-audit-{cohort_id}.jsonl"',
        },
    )


class SlotHistoryEvent(BaseModel):
    event_type: str
    generation: int
    payload: dict[str, Any]
    occurred_at: str
    hash: str


class SlotHistoryResponse(BaseModel):
    slot_id: str
    display_id: str
    current_generation: int
    chain_verified: bool  # ハッシュチェーン完全性(FR-GV-03)
    events: list[SlotHistoryEvent]


@router.get("/lineage/slots/{slot_id}/history", response_model=SlotHistoryResponse)
async def slot_history(slot_id: str) -> SlotHistoryResponse:
    cohort = STORE.find_cohort_by_slot(slot_id)
    slot = next(s for s in cohort.slots if s.slot_id == slot_id)

    verified = True
    try:
        verify_chain(slot.events)
    except Exception:
        verified = False

    return SlotHistoryResponse(
        slot_id=slot.slot_id,
        display_id=slot.display_id,
        current_generation=slot.generation,
        chain_verified=verified,
        events=[
            SlotHistoryEvent(
                event_type=str(e.event_type),
                generation=e.generation,
                payload=e.payload,
                occurred_at=e.occurred_at.isoformat(),
                hash=e.hash.hex(),
            )
            for e in slot.events
        ],
    )
