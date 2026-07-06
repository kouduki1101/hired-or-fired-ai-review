"""自律提案の調停(明細書 ¶0228-0230 / FR-GV-04)。

各スロットのエージェントは「Rehatch申請」「役割特化申請」を提出できる。
オーケストレーションは提案を無条件に受け入れず、群全体の状態(健全性)と
照合して承認/否認を判定する。例: 群が過分散(CHAOTIC)の間は新規Rehatchを凍結。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aios_core.types import HealthStatus


class ProposalKind(StrEnum):
    REHATCH_REQUEST = "rehatch_request"
    ROLE_CHANGE = "role_change"


@dataclass(frozen=True)
class ArbitrationDecision:
    approved: bool
    rule: str  # 適用ルール(機械可読、リネージ記録用)
    message: str  # 人間可読の理由


def arbitrate_proposal(
    kind: ProposalKind,
    health: HealthStatus,
    *,
    slot_rehatch_locked: bool = False,
) -> ArbitrationDecision:
    """群全体状態との照合による承認/否認(決定的ルール)。"""
    if slot_rehatch_locked:
        return ArbitrationDecision(
            approved=False,
            rule="slot_locked",
            message="削除保護フラグが有効なため申請を受理できません",
        )

    if kind == ProposalKind.REHATCH_REQUEST:
        if health == HealthStatus.CHAOTIC:
            # 過分散時の凍結(¶0230の例)
            return ArbitrationDecision(
                approved=False,
                rule="chaotic_freeze",
                message="群が過分散状態のため新規Rehatchを凍結中です(現状維持を指示)",
            )
        if health == HealthStatus.UNKNOWN:
            return ArbitrationDecision(
                approved=False,
                rule="no_observation",
                message="群状態が未観測のため判定を保留します",
            )
        return ArbitrationDecision(
            approved=True,
            rule="diversity_recovery" if health == HealthStatus.FIXED else "normal_grant",
            message="群状態と整合するため承認します",
        )

    # ROLE_CHANGE: 安定時のみ許可(不安定時の役割変更は挙動を悪化させ得る)
    if health == HealthStatus.STABLE:
        return ArbitrationDecision(
            approved=True, rule="stable_grant", message="群が安定状態のため役割変更を承認します"
        )
    return ArbitrationDecision(
        approved=False,
        rule="unstable_hold",
        message=f"群が{health}状態のため役割変更を保留します",
    )
