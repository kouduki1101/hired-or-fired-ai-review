"""エージェント自律提案API(明細書 変形例(5) ¶0228-0230 / FR-GV-04)。

スロット側(エージェント/ラッパー)がRehatch申請・役割変更申請を提出し、
オーケストレーションが群全体状態と照合して承認/否認を即時判定する。
判定と理由はスロットの運用履歴イベントとして記録される(リネージ)。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from aios_core.lineage.events import SlotEventType
from aios_core.policy.arbitration import ProposalKind, arbitrate_proposal
from aios_core.types import HealthStatus
from fastapi import APIRouter
from pydantic import BaseModel, Field

from aios_api.store import STORE

router = APIRouter(tags=["proposals"])


class SubmitProposalRequest(BaseModel):
    slot_id: str
    kind: ProposalKind
    rationale: dict[str, Any] = Field(default_factory=dict)  # 損失停滞等、エージェント側の根拠


class ProposalResponse(BaseModel):
    proposal_id: str
    slot_id: str
    kind: ProposalKind
    decision: str  # approved / rejected
    rule: str
    message: str
    cohort_health: HealthStatus


@router.post("/proposals", status_code=201, response_model=ProposalResponse)
async def submit_proposal(req: SubmitProposalRequest) -> ProposalResponse:
    cohort = STORE.find_cohort_by_slot(req.slot_id)
    slot = next(s for s in cohort.slots if s.slot_id == req.slot_id)
    now = datetime.now(UTC)
    proposal_id = str(uuid.uuid4())

    last = STORE.last_cycle(cohort.cohort_id)
    health = last.health if last else HealthStatus.UNKNOWN

    decision = arbitrate_proposal(req.kind, health, slot_rehatch_locked=slot.rehatch_lock)

    slot.record(
        SlotEventType.PROPOSAL_SUBMITTED,
        {"proposal_id": proposal_id, "kind": str(req.kind), "rationale": req.rationale},
        now,
    )
    slot.record(
        SlotEventType.PROPOSAL_DECIDED,
        {
            "proposal_id": proposal_id,
            "decision": "approved" if decision.approved else "rejected",
            "rule": decision.rule,
            "health": str(health),
        },
        now,
    )

    return ProposalResponse(
        proposal_id=proposal_id,
        slot_id=req.slot_id,
        kind=req.kind,
        decision="approved" if decision.approved else "rejected",
        rule=decision.rule,
        message=decision.message,
        cohort_health=health,
    )
