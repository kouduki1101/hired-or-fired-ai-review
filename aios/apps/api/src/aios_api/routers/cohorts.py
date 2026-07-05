"""コホート/スロットAPI(P0: インメモリ実装)。

契約上の要点:
- スロットのDELETEエンドポイントは定義しない(No-Delete by Design、請求項2)
- スロットの追加生成エンドポイントは定義しない。コホート作成(卵層)時のみ生成(請求項10)
- 休止は status 変更(PUT .../dormant)であり削除ではない
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from aios_core.types import CohortPhase, SlotStatus
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["cohorts"])

# ---- P0 インメモリストア(P1でpackages/storageへ置換) ----
_COHORTS: dict[str, dict] = {}


class CreateCohortRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slot_count: int = Field(ge=2, le=1000)
    adapter_kind: str = "anthropic_agent"
    ema_alpha: float = Field(default=0.1, gt=0.0, le=1.0)


class SlotSummary(BaseModel):
    slot_id: str
    display_id: str
    status: SlotStatus
    generation: int
    maturity: int
    fitness: float | None = None
    rehatch_lock: bool = False


class CohortResponse(BaseModel):
    cohort_id: str
    name: str
    phase: CohortPhase
    slot_count: int
    slots: list[SlotSummary]


@router.post("/cohorts", status_code=201, response_model=CohortResponse)
async def create_cohort(req: CreateCohortRequest) -> CohortResponse:
    """卵層(Phase1): K体のスロットを生成し、即時に定常運用フェーズへ遷移する。

    P1で初期教師ベクトルT_0・シード構成・キャリブレーションを追加する。
    """
    cohort_id = str(uuid.uuid4())
    slots = [
        SlotSummary(
            slot_id=str(uuid.uuid4()),
            display_id=f"{i + 1:03d}",
            status=SlotStatus.ACTIVE,
            generation=0,
            maturity=0,
        )
        for i in range(req.slot_count)
    ]
    cohort = {
        "cohort_id": cohort_id,
        "name": req.name,
        "phase": CohortPhase.OPERATING,  # P0では初期化を同期簡略化
        "slot_count": req.slot_count,
        "slots": slots,
        "created_at": datetime.now(UTC),
    }
    _COHORTS[cohort_id] = cohort
    return CohortResponse(**{k: cohort[k] for k in CohortResponse.model_fields})


@router.get("/cohorts", response_model=list[CohortResponse])
async def list_cohorts() -> list[CohortResponse]:
    return [
        CohortResponse(**{k: c[k] for k in CohortResponse.model_fields})
        for c in _COHORTS.values()
    ]


@router.get("/cohorts/{cohort_id}", response_model=CohortResponse)
async def get_cohort(cohort_id: str) -> CohortResponse:
    c = _COHORTS.get(cohort_id)
    if c is None:
        raise HTTPException(status_code=404, detail="cohort not found")
    return CohortResponse(**{k: c[k] for k in CohortResponse.model_fields})


class LockRequest(BaseModel):
    rehatch_lock: bool


@router.put("/cohorts/{cohort_id}/slots/{slot_id}/lock", response_model=SlotSummary)
async def set_slot_lock(cohort_id: str, slot_id: str, req: LockRequest) -> SlotSummary:
    """削除保護フラグ(明細書 図7)の設定。"""
    c = _COHORTS.get(cohort_id)
    if c is None:
        raise HTTPException(status_code=404, detail="cohort not found")
    for i, s in enumerate(c["slots"]):
        if s.slot_id == slot_id:
            updated = s.model_copy(update={"rehatch_lock": req.rehatch_lock})
            c["slots"][i] = updated
            return updated
    raise HTTPException(status_code=404, detail="slot not found")
