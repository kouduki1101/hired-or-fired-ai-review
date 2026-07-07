"""OIDC Bearer トークン検証(SSO、FR-TN-02 / NFR-SE-05)。

`Authorization: Bearer <JWT>` を検証し、主体(Principal)を解決する。

- 署名検証は PyJWT に委譲(HS256=共有秘密 / RS256=JWKS もしくは静的公開鍵)
- `iss`(発行者)・`aud`(オーディエンス)・`exp`(失効)を検証
- テナントは `tenant_claim`、ロールは `roles_claim`(ドット区切りでネスト可、
  例 Keycloak 形式 "realm_access.roles")から抽出し、最も高いロールを採用

本番では `jwks_uri` を設定し IdP(Auth0/Keycloak/Entra ID 等)の公開鍵で検証する。
テストや対称鍵デプロイでは `hmac_secret` を用いる。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import jwt
from jwt import InvalidTokenError, PyJWKClient

from aios_api.rbac import Principal, Role


class OidcError(Exception):
    """トークン検証の失敗(呼び出し側で 401 に写像する)。"""


@dataclass
class OidcConfig:
    """OIDC 検証設定。issuer と audience は必須。鍵ソースは3系統のいずれか。"""

    issuer: str
    audience: str
    algorithms: list[str] = field(default_factory=lambda: ["RS256"])
    tenant_claim: str = "tenant"
    roles_claim: str = "roles"
    # ロール名の写像(IdP のロール文字列 -> AIOS ロール)。未指定なら同名解釈。
    role_map: dict[str, Role] = field(default_factory=dict)
    default_role: Role = Role.VIEWER
    # 鍵ソース(優先順: hmac_secret > jwks(静的) > jwks_uri)
    hmac_secret: str | None = None
    jwks: dict[str, Any] | None = None
    jwks_uri: str | None = None

    @classmethod
    def from_env(cls) -> OidcConfig | None:
        """AIOS_OIDC_ISSUER 等の環境変数から構築。未設定なら None。"""
        issuer = os.environ.get("AIOS_OIDC_ISSUER")
        audience = os.environ.get("AIOS_OIDC_AUDIENCE")
        if not issuer or not audience:
            return None
        algos = os.environ.get("AIOS_OIDC_ALGORITHMS", "RS256")
        return cls(
            issuer=issuer,
            audience=audience,
            algorithms=[a.strip() for a in algos.split(",") if a.strip()],
            tenant_claim=os.environ.get("AIOS_OIDC_TENANT_CLAIM", "tenant"),
            roles_claim=os.environ.get("AIOS_OIDC_ROLES_CLAIM", "roles"),
            hmac_secret=os.environ.get("AIOS_OIDC_HMAC_SECRET"),
            jwks_uri=os.environ.get("AIOS_OIDC_JWKS_URI"),
        )


def _dig(claims: dict[str, Any], dotted: str) -> Any:
    """ドット区切りのクレームパスを辿る("realm_access.roles" 等)。"""
    node: Any = claims
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class OidcVerifier:
    """OidcConfig に基づき Bearer トークンを検証する。"""

    def __init__(self, config: OidcConfig) -> None:
        self._cfg = config
        self._jwk_client: PyJWKClient | None = (
            PyJWKClient(config.jwks_uri) if config.jwks_uri else None
        )

    def _signing_key(self, token: str) -> Any:
        cfg = self._cfg
        if cfg.hmac_secret is not None:
            return cfg.hmac_secret
        if cfg.jwks is not None:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            for key in cfg.jwks.get("keys", []):
                if kid is None or key.get("kid") == kid:
                    return jwt.PyJWK.from_dict(key).key
            raise OidcError("no matching JWK for token kid")
        if self._jwk_client is not None:
            return self._jwk_client.get_signing_key_from_jwt(token).key
        raise OidcError("no signing key source configured (hmac_secret/jwks/jwks_uri)")

    def verify(self, token: str) -> Principal:
        cfg = self._cfg
        try:
            key = self._signing_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=cfg.algorithms,
                audience=cfg.audience,
                issuer=cfg.issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
        except (InvalidTokenError, OidcError) as exc:
            raise OidcError(f"invalid bearer token: {exc}") from exc

        tenant = claims.get(cfg.tenant_claim)
        if not tenant or not isinstance(tenant, str):
            raise OidcError(f"missing tenant claim {cfg.tenant_claim!r}")

        role = self._resolve_role(claims)
        subject = str(claims.get("sub", "unknown"))
        return Principal(tenant=tenant, role=role, subject=subject, auth_method="oidc")

    def _resolve_role(self, claims: dict[str, Any]) -> Role:
        raw = _dig(claims, self._cfg.roles_claim)
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return self._cfg.default_role
        best = self._cfg.default_role
        for name in raw:
            mapped = self._cfg.role_map.get(name)
            if mapped is None:
                try:
                    mapped = Role.parse(str(name))
                except ValueError:
                    continue
            best = max(best, mapped)
        return best
