"""群指標の参照と制御サイクルの実行(FR-MT / FR-LC-03 / docs/05 §2.3)。

P1では制御サイクルはオンデマンド実行(POST cycles/run)。
P2で常駐スケジューラ(CycleScheduler)がこのエンドポイントと同じ処理を周期駆動する。
"""

from __future__ import annotations

import math

from aios_core.types import HealthStatus
from aios_orchestrator.cycle import CycleConfig, run_cycle
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aios_api.store import STORE

router = APIRouter(tags=["metrics"])


class RehatchedSlot(BaseModel):
    slot_id: str
    reason: str
    committed: bool
    new_generation: int


class QuarantinedSlot(BaseModel):
    slot_id: str
    label: str
    similarity: float


class CycleSummary(BaseModel):
    step_no: int
    health: HealthStatus
    dissipation: float | None
    tv_drift: float
    fitness_mean: float | None
    lr_correction: float
    noise_amount: float
    rehatched: list[RehatchedSlot]
    quarantined: list[QuarantinedSlot]
    stabilization_point: bool
    probe_missing: int
    dry_run: bool


class CurrentMetrics(BaseModel):
    cohort_id: str
    step_no: int
    loop_state: str
    health: HealthStatus
    dissipation: float | None
    dynamics: dict[str, float]
    thresholds: dict[str, float]
    last_cycle: CycleSummary | None


def _nan_to_none(x: float) -> float | None:
    return None if math.isnan(x) else x


def _summary(result) -> CycleSummary:
    return CycleSummary(
        step_no=result.step_no,
        health=result.health,
        dissipation=_nan_to_none(result.dissipation),
        tv_drift=result.tv_drift,
        fitness_mean=_nan_to_none(result.fitness_mean),
        lr_correction=result.lr_correction,
        noise_amount=result.noise_amount,
        rehatched=[
            RehatchedSlot(
                slot_id=o.slot_id,
                reason=o.reason,
                committed=o.committed,
                new_generation=o.new_generation,
            )
            for o in result.rehatched
        ],
        quarantined=[
            QuarantinedSlot(slot_id=q.slot_id, label=q.label, similarity=q.similarity)
            for q in result.quarantined
        ],
        stabilization_point=result.stabilization_point,
        probe_missing=result.probe_missing,
        dry_run=result.dry_run,
    )


class LoopControlRequest(BaseModel):
    action: str  # pause / resume / dry_run_on / dry_run_off


class LoopStateResponse(BaseModel):
    cohort_id: str
    loop_state: str


@router.post("/cohorts/{cohort_id}/loop", response_model=LoopStateResponse)
async def control_loop(cohort_id: str, req: LoopControlRequest) -> LoopStateResponse:
    """ループ制御(FR-LC-03 / FR-UI-07)。操作は監査対象。"""
    STORE.get_cohort(cohort_id)  # 404チェック
    transitions = {
        "pause": "PAUSED",
        "resume": "RUNNING",
        "dry_run_on": "DRY_RUN",
        "dry_run_off": "RUNNING",
    }
    if req.action not in transitions:
        raise HTTPException(status_code=422, detail=f"unknown action: {req.action}")
    STORE.set_loop_state(cohort_id, transitions[req.action])
    return LoopStateResponse(cohort_id=cohort_id, loop_state=STORE.loop_state(cohort_id))


@router.post("/cohorts/{cohort_id}/cycles/run", response_model=CycleSummary)
async def run_control_cycle(cohort_id: str, dry_run: bool = False) -> CycleSummary:
    """制御サイクルを1回実行する(明細書 図10のメインループ1周)。

    ループ状態を尊重する: PAUSED中は409、DRY_RUN中は強制的に判断のみ。
    (常駐駆動は aios_orchestrator.scheduler.CycleScheduler が同じ規則で行う)
    """
    cohort = STORE.get_cohort(cohort_id)
    loop_state = STORE.loop_state(cohort_id)
    if loop_state == "PAUSED":
        raise HTTPException(status_code=409, detail="control loop is paused")
    effective_dry_run = dry_run or loop_state == "DRY_RUN"
    result = await run_cycle(cohort, CycleConfig(dry_run=effective_dry_run))
    STORE.set_last_cycle(cohort_id, result)
    return _summary(result)


@router.get("/cohorts/{cohort_id}/metrics/history")
async def metrics_history(cohort_id: str, limit: int = 100) -> list[dict]:
    """サイクル時系列(ダッシュボードのトレンド&追従グラフ入力、FR-UI-03)。"""
    STORE.get_cohort(cohort_id)  # 404チェック
    return STORE.cycle_history(cohort_id)[-max(1, min(limit, 200)):]


@router.get("/cohorts/{cohort_id}/metrics/current", response_model=CurrentMetrics)
async def current_metrics(cohort_id: str) -> CurrentMetrics:
    cohort = STORE.get_cohort(cohort_id)
    last = STORE.last_cycle(cohort_id)
    return CurrentMetrics(
        cohort_id=cohort_id,
        step_no=cohort.step_no,
        loop_state=STORE.loop_state(cohort_id),
        health=last.health if last else HealthStatus.UNKNOWN,
        dissipation=_nan_to_none(last.dissipation) if last else None,
        dynamics={
            "lr_correction": cohort.dynamics.lr_correction,
            "noise_amount": cohort.dynamics.noise_amount,
        },
        thresholds={
            "lower": cohort.thresholds.lower,
            "upper": cohort.thresholds.upper,
        },
        last_cycle=_summary(last) if last else None,
    )
