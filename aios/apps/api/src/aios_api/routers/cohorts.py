"""コホート/スロットAPI(P1: CohortRuntimeベースのライブデモ実装)。

契約上の要点(apps/api/tests/contract で恒常回帰):
- スロットのDELETEエンドポイントは定義しない(No-Delete by Design、請求項2)
- スロットの追加生成エンドポイントは定義しない。卵層=コホート作成時のみ(請求項10)
"""

from __future__ import annotations

from aios_core.types import CohortPhase, SlotStatus
from aios_orchestrator.runtime import CohortRuntime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aios_api.store import STORE

router = APIRouter(tags=["cohorts"])


class CreateCohortRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slot_count: int = Field(ge=2, le=1000)
    adapter_kind: str = "fake_agent"  # P1デモはfake固定。P2でanthropic_agent等を解放
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


_NAMES: dict[str, str] = {}  # cohort_id -> name(表示用)


def _to_response(cohort: CohortRuntime) -> CohortResponse:
    return CohortResponse(
        cohort_id=cohort.cohort_id,
        name=_NAMES.get(cohort.cohort_id, ""),
        phase=cohort.phase,
        slot_count=len(cohort.slots),
        slots=[
            SlotSummary(
                slot_id=s.slot_id,
                display_id=s.display_id,
                status=s.status,
                generation=s.generation,
                maturity=s.maturity,
                fitness=s.fitness_hat,
                rehatch_lock=s.rehatch_lock,
            )
            for s in cohort.slots
        ],
    )


@router.post("/cohorts", status_code=201, response_model=CohortResponse)
async def create_cohort(req: CreateCohortRequest) -> CohortResponse:
    """卵層(Phase1): K体を生成し定常運用フェーズへ遷移する。"""
    cohort = STORE.create_cohort(
        name=req.name, slot_count=req.slot_count, ema_alpha=req.ema_alpha
    )
    _NAMES[cohort.cohort_id] = req.name
    return _to_response(cohort)


@router.get("/cohorts", response_model=list[CohortResponse])
async def list_cohorts() -> list[CohortResponse]:
    return [_to_response(c) for c in STORE.list_cohorts()]


@router.get("/cohorts/{cohort_id}", response_model=CohortResponse)
async def get_cohort(cohort_id: str) -> CohortResponse:
    return _to_response(STORE.get_cohort(cohort_id))


class LockRequest(BaseModel):
    rehatch_lock: bool


@router.put("/cohorts/{cohort_id}/slots/{slot_id}/lock", response_model=SlotSummary)
async def set_slot_lock(cohort_id: str, slot_id: str, req: LockRequest) -> SlotSummary:
    """削除保護フラグ(明細書 図7)の設定。"""
    cohort = STORE.get_cohort(cohort_id)
    for s in cohort.slots:
        if s.slot_id == slot_id:
            s.rehatch_lock = req.rehatch_lock
            return SlotSummary(
                slot_id=s.slot_id,
                display_id=s.display_id,
                status=s.status,
                generation=s.generation,
                maturity=s.maturity,
                fitness=s.fitness_hat,
                rehatch_lock=s.rehatch_lock,
            )
    raise HTTPException(status_code=404, detail="slot not found")
