"""群指標の参照と制御サイクルの実行(FR-MT / FR-LC-03 / docs/05 §2.3)。

P1では制御サイクルはオンデマンド実行(POST cycles/run)。
P2で常駐スケジューラ(CycleScheduler)がこのエンドポイントと同じ処理を周期駆動する。
"""

from __future__ import annotations

import math

from aios_core.types import HealthStatus
from aios_orchestrator.cycle import CycleConfig, run_cycle
from fastapi import APIRouter
from pydantic import BaseModel

from aios_api.store import STORE

router = APIRouter(tags=["metrics"])


class RehatchedSlot(BaseModel):
    slot_id: str
    reason: str
    committed: bool
    new_generation: int


class CycleSummary(BaseModel):
    step_no: int
    health: HealthStatus
    dissipation: float | None
    tv_drift: float
    fitness_mean: float | None
    lr_correction: float
    noise_amount: float
    rehatched: list[RehatchedSlot]
    probe_missing: int
    dry_run: bool


class CurrentMetrics(BaseModel):
    cohort_id: str
    step_no: int
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
        probe_missing=result.probe_missing,
        dry_run=result.dry_run,
    )


@router.post("/cohorts/{cohort_id}/cycles/run", response_model=CycleSummary)
async def run_control_cycle(cohort_id: str, dry_run: bool = False) -> CycleSummary:
    """制御サイクルを1回実行する(明細書 図10のメインループ1周)。"""
    cohort = STORE.get_cohort(cohort_id)
    result = await run_cycle(cohort, CycleConfig(dry_run=dry_run))
    STORE.set_last_cycle(cohort_id, result)
    return _summary(result)


@router.get("/cohorts/{cohort_id}/metrics/current", response_model=CurrentMetrics)
async def current_metrics(cohort_id: str) -> CurrentMetrics:
    cohort = STORE.get_cohort(cohort_id)
    last = STORE.last_cycle(cohort_id)
    return CurrentMetrics(
        cohort_id=cohort_id,
        step_no=cohort.step_no,
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
