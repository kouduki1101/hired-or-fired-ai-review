"""エラーカタログ(docs/05 §5: RFC 9457 Problem Details の aios_code に対応)。"""

from __future__ import annotations


class AiosError(Exception):
    """機械可読コードを持つ基底エラー。"""

    code: str = "internal_error"
    status: int = 500

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.__class__.__name__)


class PhaseLockedError(AiosError):
    """請求項10: 定常運用フェーズでのスロット追加生成等の禁止操作。"""

    code = "phase_locked"
    status = 409


class NoDeleteError(AiosError):
    """No-Delete by Design: スロット削除は仕様として存在しない。"""

    code = "no_delete"
    status = 405


class ApprovalRequiredError(AiosError):
    code = "approval_required"
    status = 202


class SlotLockedError(AiosError):
    code = "slot_locked"
    status = 409


class QuarantinedError(AiosError):
    code = "quarantined"
    status = 409


class BudgetExceededError(AiosError):
    code = "budget_exceeded"
    status = 429
