"""承認ワークフロー(FR-GV-05 / docs/05 §2.10)。

approval_mode=manual のコホートでは、Rehatch実行・次元拡張が承認キューを経由する。
承認・却下の判断は監査対象(承認レコード+スロットイベントに残る)。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aios_orchestrator.cycle import rehatch_slot
from aios_orchestrator.scaling import expand_cohort_dimension
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aios_api.store import STORE

router = APIRouter(tags=["approvals"])


class ApprovalItem(BaseModel):
    approval_id: str
    cohort_id: str
    action_type: str
    payload: dict[str, Any]
    status: str
    requested_at: str
    decided_at: str | None


class DecisionRequest(BaseModel):
    comment: str = Field(default="", max_length=1000)


@router.get("/approvals", response_model=list[ApprovalItem])
async def list_approvals(status: str | None = None) -> list[ApprovalItem]:
    return [ApprovalItem(**a) for a in STORE.list_approvals(status)]


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalItem)
async def approve(approval_id: str, req: DecisionRequest) -> ApprovalItem:
    """承認: 保留中アクションを実行する。"""
    approval = STORE.get_approval(approval_id)
    if approval["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"already {approval['status']}")

    cohort = STORE.get_cohort(approval["cohort_id"])
    if approval["action_type"] == "rehatch":
        outcome = await rehatch_slot(
            cohort, approval["payload"]["slot_id"], approval["payload"]["reason"]
        )
        approval["payload"] = {
            **approval["payload"],
            "committed": outcome.committed,
            "new_generation": outcome.new_generation,
        }
        if outcome.committed:
            STORE.bump_usage(cohort.cohort_id, "rehatches_committed")
    elif approval["action_type"] == "dimension_expansion":
        new_dim = await expand_cohort_dimension(
            cohort,
            approval["payload"]["added_dims"],
            approval["payload"]["axis_labels"],
        )
        approval["payload"] = {**approval["payload"], "new_dimension": new_dim}
    else:
        raise HTTPException(status_code=422, detail="unknown action_type")

    approval["status"] = "approved"
    approval["decided_at"] = datetime.now(UTC).isoformat()
    await STORE.persist(approval["cohort_id"])
    return ApprovalItem(**approval)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalItem)
async def reject(approval_id: str, req: DecisionRequest) -> ApprovalItem:
    """却下: アクションは実行されず、判断のみ記録される。"""
    approval = STORE.get_approval(approval_id)
    if approval["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"already {approval['status']}")
    approval["status"] = "rejected"
    approval["decided_at"] = datetime.now(UTC).isoformat()
    approval["payload"] = {**approval["payload"], "comment": req.comment}
    return ApprovalItem(**approval)
