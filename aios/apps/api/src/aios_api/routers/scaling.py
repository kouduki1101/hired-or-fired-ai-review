"""次元拡張スケーリングAPI(請求項9 / FR-SC / docs/05 §2.6)。

スロット数を維持したまま教師ベクトルの次元数を拡張する。
価値軸ラベルは全追加次元に必須(¶0098)。縮小は提供しない(監査互換性)。
"""

from __future__ import annotations

from aios_orchestrator.scaling import expand_cohort_dimension
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aios_api.store import STORE

router = APIRouter(tags=["scaling"])


class ExpandRequest(BaseModel):
    added_dims: int = Field(ge=1, le=1024)
    axis_labels: list[str] = Field(min_length=1)


class ExpandResponse(BaseModel):
    cohort_id: str
    previous_dimension: int
    new_dimension: int
    slot_count: int  # 請求項9: モデル数は維持される


@router.post("/cohorts/{cohort_id}/scaling/expand", response_model=ExpandResponse)
async def expand_dimension(cohort_id: str, req: ExpandRequest) -> ExpandResponse:
    cohort = STORE.get_cohort(cohort_id)
    previous = int(cohort.teacher_vector.shape[0])
    try:
        new_dim = await expand_cohort_dimension(cohort, req.added_dims, req.axis_labels)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    await STORE.persist(cohort_id)
    return ExpandResponse(
        cohort_id=cohort_id,
        previous_dimension=previous,
        new_dimension=new_dim,
        slot_count=len(cohort.slots),
    )


class ValueAxis(BaseModel):
    dim_index: int
    label: str


class AxesResponse(BaseModel):
    cohort_id: str
    dimension: int
    axes: list[ValueAxis]  # 拡張で追加された価値軸(初期次元は無名)


@router.get("/cohorts/{cohort_id}/scaling/axes", response_model=AxesResponse)
async def list_axes(cohort_id: str) -> AxesResponse:
    cohort = STORE.get_cohort(cohort_id)
    return AxesResponse(
        cohort_id=cohort_id,
        dimension=int(cohort.teacher_vector.shape[0]),
        axes=[
            ValueAxis(dim_index=i, label=label)
            for i, label in sorted(cohort.value_axes.items())
        ],
    )
