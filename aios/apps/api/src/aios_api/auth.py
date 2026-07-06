"""認証(APIキー / OIDC Bearer)+ RBAC + テナントコンテキスト(FR-TN-01/02)。

認証は2系統:
- `X-API-Key`: 設定は AIOS_API_KEYS="key1:tenant-a,key2:tenant-b"。
  APIキーは既定で ADMIN(サービスアカウント相当)。
- `Authorization: Bearer <JWT>`: OIDC 設定(AIOS_OIDC_*)がある場合のみ有効。
  テナント・ロールはトークンのクレームから解決する(oidc.py)。

いずれの経路でも解決された主体(Principal)を元に、
- テナントを ContextVar 経由でストア層へ伝播(NFR-SE-02)
- ロールと要求ロール(rbac.required_role)を突き合わせ、不足なら 403(NFR-SE-05)

キーも OIDC も未設定(開発モード)では認証をスキップし、
全リクエストを ADMIN/"default" テナントとして扱う。
"""

from __future__ import annotations

import os
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from aios_api.oidc import OidcConfig, OidcError, OidcVerifier
from aios_api.rbac import Principal, Role, required_role

DEFAULT_TENANT = "default"
current_tenant: ContextVar[str] = ContextVar("aios_tenant", default=DEFAULT_TENANT)
current_principal: ContextVar[Principal | None] = ContextVar("aios_principal", default=None)

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
    """APIキー/Bearer を検証し主体を解決、RBAC を適用する。

    api_keys も oidc も未設定なら素通し(devモード= ADMIN/default)。
    """

    def __init__(  # type: ignore[no-untyped-def]
        self,
        app,
        api_keys: dict[str, str],
        oidc: OidcConfig | None = None,
    ) -> None:
        super().__init__(app)
        self._api_keys = api_keys
        self._verifier = OidcVerifier(oidc) if oidc is not None else None

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        path = request.url.path
        auth_enabled = bool(self._api_keys) or self._verifier is not None

        if not auth_enabled or path in EXEMPT_PATHS:
            principal = Principal(DEFAULT_TENANT, Role.ADMIN, "dev", "dev")
        else:
            resolved = self._authenticate(request)
            if isinstance(resolved, Response):
                return resolved
            principal = resolved
            # RBAC: 要求ロールに満たなければ 403
            if principal.role < required_role(request.method, path):
                return _forbidden(
                    f"role {principal.role.name.lower()} lacks permission for "
                    f"{request.method} {path}"
                )

        tenant_token = current_tenant.set(principal.tenant)
        principal_token = current_principal.set(principal)
        try:
            return await call_next(request)
        finally:
            current_tenant.reset(tenant_token)
            current_principal.reset(principal_token)

    def _authenticate(self, request: Request) -> Principal | Response:
        """APIキー優先、無ければ Bearer。失敗時は 401 レスポンスを返す。"""
        api_key = request.headers.get("X-API-Key")
        if api_key is not None:
            tenant = self._api_keys.get(api_key)
            if tenant is None:
                return _unauthorized("invalid API key")
            return Principal(tenant, Role.ADMIN, f"apikey:{tenant}", "api_key")

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and self._verifier is not None:
            token = auth_header[len("Bearer ") :].strip()
            try:
                return self._verifier.verify(token)
            except OidcError as exc:
                return _unauthorized(str(exc))

        if self._verifier is not None:
            return _unauthorized("missing X-API-Key or Bearer token")
        return _unauthorized("missing X-API-Key header")


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
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "type": "https://docs.aios.example/errors/forbidden",
            "title": "forbidden",
            "detail": detail,
            "aios_code": "forbidden",
        },
        media_type="application/problem+json",
    )
