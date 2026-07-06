"""タスク投入とルーティング(請求項8 / FR-RT / docs/05 §2.2)。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from aios_adapters.spi import TaskInput
from aios_core.lineage.events import SlotEventType
from aios_core.policy.routing import TaskMeta, route_task
from aios_core.types import Cluster, TaskDifficulty, TaskImportance
from fastapi import APIRouter
from pydantic import BaseModel, Field

from aios_api.store import STORE

router = APIRouter(tags=["tasks"])


class TaskMetadata(BaseModel):
    importance: TaskImportance = TaskImportance.NORMAL
    difficulty: TaskDifficulty = TaskDifficulty.NORMAL
    category: str | None = None


class SubmitTaskRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: TaskMetadata = Field(default_factory=TaskMetadata)


class RoutedTo(BaseModel):
    slot_id: str
    display_id: str
    generation: int
    cluster: Cluster


class TaskResponse(BaseModel):
    task_id: str
    output: dict[str, Any]
    routed_to: RoutedTo
    routing_reason: str


@router.post("/cohorts/{cohort_id}/tasks", response_model=TaskResponse)
async def submit_task(cohort_id: str, req: SubmitTaskRequest) -> TaskResponse:
    cohort = STORE.get_cohort(cohort_id)
    now = datetime.now(UTC)
    task_id = str(uuid.uuid4())

    meta = TaskMeta(
        importance=req.metadata.importance,
        difficulty=req.metadata.difficulty,
        category=req.metadata.category,
    )
    decision = route_task(meta, [s.view() for s in cohort.slots])
    slot = next(s for s in cohort.slots if s.slot_id == decision.chosen_slot_id)

    # リネージ: 担当時点の世代・判断理由をイベントとして固定記録(FR-GV-01)
    slot.record(
        SlotEventType.TASK_ASSIGNED,
        {"task_id": task_id, "reason": decision.reason, "cluster": str(decision.cluster)},
        now,
    )
    out = await slot.adapter.invoke(TaskInput(task_id=task_id, payload=req.input), cohort.dynamics)
    slot.record(SlotEventType.TASK_COMPLETED, {"task_id": task_id, "maturity_delta": 1}, now)
    slot.maturity += 1
    STORE.record_assignment(cohort_id, slot.slot_id)

    # リネージ: 担当時点の世代・ステップ・制御値を固定記録(FR-GV-01)
    STORE.record_task(
        task_id,
        {
            "task_id": task_id,
            "cohort_id": cohort_id,
            "slot_id": slot.slot_id,
            "display_id": slot.display_id,
            "generation": slot.generation,
            "step_no": cohort.step_no,
            "cluster": str(decision.cluster),
            "routing_reason": decision.reason,
            "dynamics": {
                "lr_correction": cohort.dynamics.lr_correction,
                "noise_amount": cohort.dynamics.noise_amount,
            },
            "requested_at": now.isoformat(),
        },
    )

    return TaskResponse(
        task_id=task_id,
        output=out.payload,
        routed_to=RoutedTo(
            slot_id=slot.slot_id,
            display_id=slot.display_id,
            generation=slot.generation,
            cluster=decision.cluster,
        ),
        routing_reason=decision.reason,
    )
