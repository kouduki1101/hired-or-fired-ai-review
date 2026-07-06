"""APIキー認証とテナントコンテキスト(FR-TN-01/02)。

- キーは `X-API-Key` ヘッダで提示。設定は AIOS_API_KEYS="key1:tenant-a,key2:tenant-b"
  または create_app(api_keys={key: tenant_id})
- キー未設定(開発モード)では認証をスキップし、全リクエストを "default" テナントとする
- 解決したテナントは ContextVar 経由でストア層に伝播し、
  コホート・承認・使用量・Webhookがテナント単位に分離される(NFR-SE-02)
- P4後半: OIDC SSO/RBACはこの層を置換する形で導入する(FR-TN-02)
"""

from __future__ import annotations

import os
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

DEFAULT_TENANT = "default"
current_tenant: ContextVar[str] = ContextVar("aios_tenant", default=DEFAULT_TENANT)

# 認証免除パス(死活監視・APIドキュメント)
EXEMPT_PATHS = {"/healthz", "/readyz", "/docs", "/openapi.json", "/redoc"}


def parse_api_keys(raw: str | None) -> dict[str, str]:
    """"key1:tenant-a,key2:tenant-b" 形式をパースする。"""
    keys: dict[str, str] = {}
    if not raw:
        return keys
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        key, _, tenant = pair.partition(":")
        if not key or not tenant:
            raise ValueError(f"invalid AIOS_API_KEYS entry (expected key:tenant): {pair!r}")
        keys[key] = tenant
    return keys


def resolve_api_keys(explicit: dict[str, str] | None) -> dict[str, str]:
    if explicit is not None:
        return dict(explicit)
    return parse_api_keys(os.environ.get("AIOS_API_KEYS"))


class AuthMiddleware(BaseHTTPMiddleware):
    """X-API-Key を検証しテナントを解決する。キー未設定時は素通し(devモード)。"""

    def __init__(self, app, api_keys: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._api_keys = api_keys

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        if not self._api_keys or request.url.path in EXEMPT_PATHS:
            tenant = DEFAULT_TENANT
        else:
            key = request.headers.get("X-API-Key")
            if key is None:
                return _unauthorized("missing X-API-Key header")
            tenant = self._api_keys.get(key)  # type: ignore[assignment]
            if tenant is None:
                return _unauthorized("invalid API key")

        token = current_tenant.set(tenant)
        try:
            return await call_next(request)
        finally:
            current_tenant.reset(token)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "type": "https://docs.aios.example/errors/unauthorized",
            "title": "unauthorized",
            "detail": detail,
            "aios_code": "unauthorized",
        },
        media_type="application/problem+json",
        headers={"WWW-Authenticate": "ApiKey"},
    )
