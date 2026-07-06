"""ロールベースアクセス制御(RBAC、FR-TN-02 / NFR-SE-05)。

主体(Principal)は APIキー認証または OIDC Bearer 認証から解決され、
テナントとロールを持つ。ロールは階層順序を持つ:

    VIEWER < OPERATOR < ADMIN

エンドポイントに必要な最小ロールは HTTP メソッド + パスから決まる
(`required_role`)。ミドルウェアが主体のロールと突き合わせ、不足すれば 403。

- VIEWER   : 参照系(GET/HEAD)
- OPERATOR : 運用操作(サイクル実行・タスク投入・隔離/復旧・pause/resume 等の書込)
- ADMIN    : 管理操作(Webhook 設定・使用量・承認の approve/reject・APIキー)

APIキーは既定で ADMIN(サービスアカウント相当)。人間ユーザーは OIDC の
ロールクレームで VIEWER/OPERATOR/ADMIN に割り当てられる想定。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Role(IntEnum):
    """階層ロール。数値の大小がそのまま権限の包含関係を表す。"""

    VIEWER = 1
    OPERATOR = 2
    ADMIN = 3

    @classmethod
    def parse(cls, raw: str) -> Role:
        try:
            return cls[raw.strip().upper()]
        except KeyError as exc:
            raise ValueError(f"unknown role: {raw!r} (viewer|operator|admin)") from exc


@dataclass(frozen=True)
class Principal:
    """認証済み主体。テナント境界(NFR-SE-02)とロール(RBAC)を保持する。"""

    tenant: str
    role: Role
    subject: str
    auth_method: str  # "api_key" | "oidc" | "dev"


_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def required_role(method: str, path: str) -> Role:
    """当該リクエストに必要な最小ロールを返す(集中ポリシー)。"""
    # 管理操作は ADMIN
    if path.startswith("/v1/admin"):
        return Role.ADMIN
    if path.startswith("/v1/approvals/") and path.endswith(("/approve", "/reject")):
        return Role.ADMIN
    # 書込系は OPERATOR 以上
    if method.upper() in _WRITE_METHODS:
        return Role.OPERATOR
    # 参照系は VIEWER 以上
    return Role.VIEWER


def is_authorized(principal: Principal, method: str, path: str) -> bool:
    return principal.role >= required_role(method, path)
