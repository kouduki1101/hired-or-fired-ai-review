"""学習系 Rehatch(蒸留/LoRA)の非同期ジョブ API(P5 / FR-RH / docs/06 §7)。

- 投入: POST /cohorts/{id}/slots/{slot_id}/rehatch/train
- 進捗+適用: POST .../rehatch/train/{job_id}/advance
  (FakeTrainer は poll のたびに前進する。完了していれば Rehatch-in-Place を実施)

ジョブ状態はプロセス内(store.training)。再起動をまたぐ耐久ジョブは本番 Trainer
実装の責務(現状は Fake)。
"""

from __future__ import annotations

from datetime import UTC, datetime

from aios_adapters.spi import RehatchStrategy
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aios_api.store import STORE

router = APIRouter(tags=["training"])


class TrainRehatchRequest(BaseModel):
    strategy: RehatchStrategy = RehatchStrategy.DISTILLATION
    max_steps: int = Field(default=10, ge=1, le=1000)
    target_fitness: float = Field(default=0.9, ge=0.0, le=1.0)


class TrainingStateResponse(BaseModel):
    job_id: str
    slot_id: str
    status: str
    progress: float
    step: int
    message: str = ""
    score: float | None = None


class AdvanceResponse(TrainingStateResponse):
    applied: bool = False  # Rehatch-in-Place を実施したか
    committed: bool | None = None  # 適用時: 確定(True)/ロールバック(False)
    generation: int | None = None  # 適用確定時の新世代


def _slot(cohort_id: str, slot_id: str):  # type: ignore[no-untyped-def]
    cohort = STORE.get_cohort(cohort_id)
    slot = next((s for s in cohort.slots if s.slot_id == slot_id), None)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    return cohort, slot


@router.post(
    "/cohorts/{cohort_id}/slots/{slot_id}/rehatch/train",
    status_code=202,
    response_model=TrainingStateResponse,
)
async def submit_training(
    cohort_id: str, slot_id: str, req: TrainRehatchRequest
) -> TrainingStateResponse:
    """学習系 Rehatch ジョブを投入する(スロットは学習中も稼働継続)。"""
    cohort, slot = _slot(cohort_id, slot_id)
    if STORE.training.active_job(slot_id) is not None:
        raise HTTPException(
            status_code=409, detail="a training job is already active for this slot"
        )
    job_id = await STORE.training.submit(
        slot,
        req.strategy,
        cohort.teacher_vector,
        datetime.now(UTC),
        max_steps=req.max_steps,
        target_fitness=req.target_fitness,
    )
    state = STORE.training.poll(job_id)
    await STORE.persist(cohort_id)
    return TrainingStateResponse(
        job_id=job_id, slot_id=slot_id, status=str(state.status),
        progress=state.progress, step=state.step, message=state.message, score=state.score,
    )


@router.post(
    "/cohorts/{cohort_id}/slots/{slot_id}/rehatch/train/{job_id}/advance",
    response_model=AdvanceResponse,
)
async def advance_training(cohort_id: str, slot_id: str, job_id: str) -> AdvanceResponse:
    """ジョブを1ステップ進め、完了していれば Rehatch-in-Place を適用する。"""
    _, slot = _slot(cohort_id, slot_id)
    outcome = await STORE.training.apply_if_ready(
        slot, job_id, STORE.get_cohort(cohort_id).teacher_vector, datetime.now(UTC)
    )
    state = STORE.training.poll(job_id)
    resp = AdvanceResponse(
        job_id=job_id, slot_id=slot_id, status=str(state.status),
        progress=state.progress, step=state.step, message=state.message, score=state.score,
    )
    if outcome is not None:
        resp.applied = True
        resp.committed = outcome.committed
        resp.generation = outcome.new_generation if outcome.committed else None
        if outcome.committed:
            STORE.bump_usage(cohort_id, "rehatches_committed")
        await STORE.notifier.emit(
            "slot.rehatched" if outcome.committed else "slot.rehatch_rolled_back",
            {"slot_id": slot_id, "strategy": "learning", "job_id": job_id},
        )
    await STORE.persist(cohort_id)
    return resp
