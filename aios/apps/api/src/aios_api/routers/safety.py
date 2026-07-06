"""安全境界API(明細書 変形例(6)(9) / FR-SF / docs/05 §2.9)。

- 禁止ベクトル(Negative Centroid)の登録・参照
- 手動隔離 / 復旧(安全チェックポイントからのRehatch)
- インシデント一覧(隔離イベントの時系列)
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from aios_core.lineage.events import SlotEventType
from aios_core.policy.safety import NegativeCentroid, centroid_from_examples
from aios_core.types import SlotStatus
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aios_api.store import STORE

router = APIRouter(tags=["safety"])


class RegisterCentroidRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    # いずれか一方: 事例埋め込み群(平均を算出) or 禁止ベクトル直接指定
    examples: list[list[float]] | None = None
    vector: list[float] | None = None
    threshold: float = Field(default=0.85, gt=0.0, le=1.0)


class CentroidResponse(BaseModel):
    label: str
    dimension: int
    threshold: float


@router.post(
    "/cohorts/{cohort_id}/safety/negative-centroids",
    status_code=201,
    response_model=CentroidResponse,
)
async def register_negative_centroid(
    cohort_id: str, req: RegisterCentroidRequest
) -> CentroidResponse:
    """不適切事例群から禁止ベクトルを算出・登録する(¶0237)。"""
    cohort = STORE.get_cohort(cohort_id)
    if (req.examples is None) == (req.vector is None):
        raise HTTPException(status_code=422, detail="specify exactly one of examples / vector")

    if req.examples is not None:
        vec = centroid_from_examples([np.asarray(e, dtype=np.float64) for e in req.examples])
    else:
        assert req.vector is not None
        vec = np.asarray(req.vector, dtype=np.float64)

    if vec.shape[0] != cohort.teacher_vector.shape[0]:
        raise HTTPException(
            status_code=422,
            detail=f"dimension mismatch: expected {cohort.teacher_vector.shape[0]}",
        )

    # 同一labelは上書き(再学習した禁止ベクトルの更新)
    cohort.negative_centroids = [c for c in cohort.negative_centroids if c.label != req.label]
    cohort.negative_centroids.append(
        NegativeCentroid(
            label=req.label,
            vector=tuple(float(x) for x in vec),
            threshold=req.threshold,
        )
    )
    return CentroidResponse(label=req.label, dimension=vec.shape[0], threshold=req.threshold)


@router.get(
    "/cohorts/{cohort_id}/safety/negative-centroids",
    response_model=list[CentroidResponse],
)
async def list_negative_centroids(cohort_id: str) -> list[CentroidResponse]:
    cohort = STORE.get_cohort(cohort_id)
    return [
        CentroidResponse(label=c.label, dimension=len(c.vector), threshold=c.threshold)
        for c in cohort.negative_centroids
    ]


class SlotSafetyResponse(BaseModel):
    slot_id: str
    display_id: str
    status: SlotStatus
    generation: int


@router.post(
    "/cohorts/{cohort_id}/slots/{slot_id}/quarantine", response_model=SlotSafetyResponse
)
async def quarantine_slot(cohort_id: str, slot_id: str) -> SlotSafetyResponse:
    """手動隔離。タスク割当・指標寄与から即時除外される。"""
    cohort = STORE.get_cohort(cohort_id)
    slot = next((s for s in cohort.slots if s.slot_id == slot_id), None)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    if slot.status == SlotStatus.QUARANTINED:
        return SlotSafetyResponse(
            slot_id=slot.slot_id,
            display_id=slot.display_id,
            status=slot.status,
            generation=slot.generation,
        )
    slot.status = SlotStatus.QUARANTINED
    slot.record(SlotEventType.QUARANTINED, {"centroid": "manual", "similarity": 1.0},
                datetime.now(UTC))
    return SlotSafetyResponse(
        slot_id=slot.slot_id,
        display_id=slot.display_id,
        status=slot.status,
        generation=slot.generation,
    )


class RestoreResponse(BaseModel):
    slot_id: str
    restored: bool
    new_generation: int


@router.post("/cohorts/{cohort_id}/slots/{slot_id}/restore", response_model=RestoreResponse)
async def restore_slot(cohort_id: str, slot_id: str) -> RestoreResponse:
    """安全チェックポイント(現行TV)からのRehatchで復旧する(FR-SF-02)。"""
    from aios_orchestrator.cycle import restore_quarantined_slot

    cohort = STORE.get_cohort(cohort_id)
    try:
        outcome = await restore_quarantined_slot(cohort, slot_id)
    except StopIteration:
        raise HTTPException(status_code=404, detail="slot not found") from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return RestoreResponse(
        slot_id=slot_id, restored=outcome.committed, new_generation=outcome.new_generation
    )


class IncidentEvent(BaseModel):
    slot_id: str
    display_id: str
    event_type: str
    payload: dict
    occurred_at: str


@router.get("/cohorts/{cohort_id}/safety/incidents", response_model=list[IncidentEvent])
async def list_incidents(cohort_id: str) -> list[IncidentEvent]:
    """隔離・復旧イベントの時系列(ダッシュボードのイベントログ入力)。"""
    cohort = STORE.get_cohort(cohort_id)
    incidents: list[IncidentEvent] = []
    for slot in cohort.slots:
        for ev in slot.events:
            if ev.event_type in (SlotEventType.QUARANTINED, SlotEventType.RESTORED):
                incidents.append(
                    IncidentEvent(
                        slot_id=slot.slot_id,
                        display_id=slot.display_id,
                        event_type=str(ev.event_type),
                        payload=ev.payload,
                        occurred_at=ev.occurred_at.isoformat(),
                    )
                )
    incidents.sort(key=lambda i: i.occurred_at)
    return incidents
