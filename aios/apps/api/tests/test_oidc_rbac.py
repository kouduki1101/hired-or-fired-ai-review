"""OIDC Bearer 認証 + RBAC(FR-TN-02 / NFR-SE-05)の結合テスト。

- HS256(共有秘密)と RS256(静的 JWKS)の双方でトークン検証を通す
- ロール別に GET/書込/管理の可否が変わることを検証
- 署名不正・失効・aud/iss 不一致・tenant クレーム欠落を 401 で弾く
"""

from __future__ import annotations

import json
import time

import jwt
import pytest
from aios_api.main import create_app
from aios_api.oidc import OidcConfig
from aios_api.rbac import Role
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ISSUER = "https://idp.example/realms/aios"
AUDIENCE = "aios-api"
SECRET = "unit-test-hmac-secret-at-least-32-bytes-long!"


def _hs_config() -> OidcConfig:
    return OidcConfig(
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=["HS256"],
        hmac_secret=SECRET,
        tenant_claim="tenant",
        roles_claim="realm_access.roles",
        role_map={"aios-admin": Role.ADMIN, "aios-operator": Role.OPERATOR},
    )


def _token(roles: list[str], *, tenant: str = "tenant-x", **overrides: object) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "exp": now + 300,
        "iat": now,
        "tenant": tenant,
        "realm_access": {"roles": roles},
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _client(cfg: OidcConfig) -> TestClient:
    # api_keys={} でもよいが、OIDC のみ有効な構成を検証する
    return TestClient(create_app(oidc=cfg))


class TestBearerAuthn:
    def test_valid_viewer_can_read(self) -> None:
        client = _client(_hs_config())
        res = client.get("/v1/cohorts", headers=_bearer(_token(["aios-operator"])))
        assert res.status_code == 200

    def test_missing_token_is_401(self) -> None:
        assert _client(_hs_config()).get("/v1/cohorts").status_code == 401

    def test_bad_signature_is_401(self) -> None:
        forged = jwt.encode(
            {"iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60,
             "tenant": "t", "realm_access": {"roles": ["aios-admin"]}},
            "wrong-secret", algorithm="HS256",
        )
        assert _client(_hs_config()).get(
            "/v1/cohorts", headers=_bearer(forged)
        ).status_code == 401

    def test_expired_is_401(self) -> None:
        expired = _token(["aios-admin"], exp=int(time.time()) - 10)
        assert _client(_hs_config()).get(
            "/v1/cohorts", headers=_bearer(expired)
        ).status_code == 401

    def test_wrong_audience_is_401(self) -> None:
        bad = _token(["aios-admin"], aud="some-other-api")
        assert _client(_hs_config()).get(
            "/v1/cohorts", headers=_bearer(bad)
        ).status_code == 401

    def test_missing_tenant_claim_is_401(self) -> None:
        now = int(time.time())
        no_tenant = jwt.encode(
            {"iss": ISSUER, "aud": AUDIENCE, "exp": now + 60,
             "realm_access": {"roles": ["aios-admin"]}},
            SECRET, algorithm="HS256",
        )
        assert _client(_hs_config()).get(
            "/v1/cohorts", headers=_bearer(no_tenant)
        ).status_code == 401


class TestRbac:
    def test_viewer_cannot_write(self) -> None:
        client = _client(_hs_config())
        # viewer ロール(role_map外の未知ロールは default=VIEWER)
        res = client.post(
            "/v1/cohorts", json={"name": "x", "slot_count": 3},
            headers=_bearer(_token(["some-unrelated-role"])),
        )
        assert res.status_code == 403
        assert res.json()["aios_code"] == "forbidden"

    def test_operator_can_write_but_not_admin(self) -> None:
        client = _client(_hs_config())
        op = _bearer(_token(["aios-operator"]))
        created = client.post("/v1/cohorts", json={"name": "y", "slot_count": 3}, headers=op)
        assert created.status_code == 201
        # 管理エンドポイントは 403
        assert client.get("/v1/admin/usage", headers=op).status_code == 403

    def test_admin_can_access_admin(self) -> None:
        client = _client(_hs_config())
        admin = _bearer(_token(["aios-admin"]))
        assert client.get("/v1/admin/usage", headers=admin).status_code == 200

    def test_operator_cannot_approve(self) -> None:
        client = _client(_hs_config())
        admin = _bearer(_token(["aios-admin"], tenant="t-appr"))
        op = _bearer(_token(["aios-operator"], tenant="t-appr"))
        cohort = client.post(
            "/v1/cohorts",
            json={"name": "z", "slot_count": 4, "approval_mode": "manual"},
            headers=admin,
        ).json()
        cid = cohort["cohort_id"]
        expand = client.post(
            f"/v1/cohorts/{cid}/scaling/expand",
            json={"added_dims": 1, "axis_labels": ["a"]},
            headers=op,
        )
        assert expand.status_code == 202  # operator は拡張申請できる
        approval_id = expand.json()["approval_id"]
        # approve は ADMIN 限定
        assert client.post(
            f"/v1/approvals/{approval_id}/approve", json={}, headers=op
        ).status_code == 403
        assert client.post(
            f"/v1/approvals/{approval_id}/approve", json={}, headers=admin
        ).status_code == 200


class TestTenantFromClaim:
    def test_bearer_tenant_isolates(self) -> None:
        client = _client(_hs_config())
        a = _bearer(_token(["aios-admin"], tenant="claim-a"))
        b = _bearer(_token(["aios-admin"], tenant="claim-b"))
        cohort = client.post(
            "/v1/cohorts", json={"name": "ca", "slot_count": 3}, headers=a
        ).json()
        cid = cohort["cohort_id"]
        assert client.get(f"/v1/cohorts/{cid}", headers=a).status_code == 200
        assert client.get(f"/v1/cohorts/{cid}", headers=b).status_code == 404


class TestRs256Jwks:
    def test_rs256_static_jwks(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk_json = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())
        jwk = json.loads(jwk_json)
        jwk["kid"] = "test-key-1"
        jwk["alg"] = "RS256"
        cfg = OidcConfig(
            issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"],
            jwks={"keys": [jwk]}, tenant_claim="tenant", roles_claim="roles",
        )
        now = int(time.time())
        token = jwt.encode(
            {"iss": ISSUER, "aud": AUDIENCE, "sub": "svc", "exp": now + 300,
             "tenant": "rs-tenant", "roles": ["admin"]},
            private_key, algorithm="RS256", headers={"kid": "test-key-1"},
        )
        client = _client(cfg)
        assert client.get("/v1/admin/usage", headers=_bearer(token)).status_code == 200

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIOS_OIDC_ISSUER", ISSUER)
        monkeypatch.setenv("AIOS_OIDC_AUDIENCE", AUDIENCE)
        monkeypatch.setenv("AIOS_OIDC_ALGORITHMS", "HS256")
        monkeypatch.setenv("AIOS_OIDC_HMAC_SECRET", SECRET)
        cfg = OidcConfig.from_env()
        assert cfg is not None and cfg.issuer == ISSUER and cfg.algorithms == ["HS256"]
