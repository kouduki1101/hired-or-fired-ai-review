"""APIキー認証+テナント分離(FR-TN-01/02 / NFR-SE-02)の結合テスト。"""

from __future__ import annotations

from aios_api.auth import parse_api_keys
from aios_api.main import create_app
from fastapi.testclient import TestClient

KEYS = {"key-alpha": "tenant-a", "key-beta": "tenant-b"}


def _client() -> TestClient:
    return TestClient(create_app(api_keys=KEYS))


def _h(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


class TestAuthentication:
    def test_missing_key_is_401(self) -> None:
        client = _client()
        res = client.get("/v1/cohorts")
        assert res.status_code == 401
        assert res.json()["aios_code"] == "unauthorized"

    def test_invalid_key_is_401(self) -> None:
        assert _client().get("/v1/cohorts", headers=_h("wrong")).status_code == 401

    def test_healthz_exempt(self) -> None:
        assert _client().get("/healthz").status_code == 200

    def test_no_keys_configured_is_open_dev_mode(self) -> None:
        client = TestClient(create_app(api_keys={}))
        assert client.get("/v1/cohorts").status_code == 200

    def test_parse_api_keys(self) -> None:
        assert parse_api_keys("k1:t1, k2:t2") == {"k1": "t1", "k2": "t2"}
        assert parse_api_keys(None) == {}
        import pytest

        with pytest.raises(ValueError):
            parse_api_keys("malformed-entry")


class TestTenantIsolation:
    def test_cohorts_invisible_across_tenants(self) -> None:
        """他テナントのコホートは一覧に出ず、直接取得も404(NFR-SE-02)。"""
        client = _client()
        cohort = client.post(
            "/v1/cohorts",
            json={"name": "alpha-cohort", "slot_count": 3},
            headers=_h("key-alpha"),
        ).json()
        cid = cohort["cohort_id"]

        # tenant-a: 見える
        assert cid in [c["cohort_id"] for c in
                       client.get("/v1/cohorts", headers=_h("key-alpha")).json()]
        # tenant-b: 一覧に出ない・直接アクセスも404
        assert cid not in [c["cohort_id"] for c in
                           client.get("/v1/cohorts", headers=_h("key-beta")).json()]
        assert client.get(f"/v1/cohorts/{cid}", headers=_h("key-beta")).status_code == 404
        assert (
            client.post(f"/v1/cohorts/{cid}/cycles/run", headers=_h("key-beta")).status_code
            == 404
        )

    def test_lineage_scoped_by_tenant(self) -> None:
        client = _client()
        cohort = client.post(
            "/v1/cohorts", json={"name": "a2", "slot_count": 3}, headers=_h("key-alpha")
        ).json()
        slot_id = cohort["slots"][0]["slot_id"]
        assert (
            client.get(f"/v1/lineage/slots/{slot_id}/history",
                       headers=_h("key-alpha")).status_code == 200
        )
        assert (
            client.get(f"/v1/lineage/slots/{slot_id}/history",
                       headers=_h("key-beta")).status_code == 404
        )

    def test_approvals_scoped_by_tenant(self) -> None:
        client = _client()
        cohort = client.post(
            "/v1/cohorts",
            json={"name": "a3", "slot_count": 4, "approval_mode": "manual"},
            headers=_h("key-alpha"),
        ).json()
        cid = cohort["cohort_id"]
        res = client.post(
            f"/v1/cohorts/{cid}/scaling/expand",
            json={"added_dims": 1, "axis_labels": ["x"]},
            headers=_h("key-alpha"),
        )
        approval_id = res.json()["approval_id"]

        assert client.get("/v1/approvals", headers=_h("key-beta")).json() == []
        assert (
            client.post(f"/v1/approvals/{approval_id}/approve", json={},
                        headers=_h("key-beta")).status_code == 404
        )
        # 自テナントは承認できる
        assert (
            client.post(f"/v1/approvals/{approval_id}/approve", json={},
                        headers=_h("key-alpha")).status_code == 200
        )

    def test_usage_scoped_by_tenant(self) -> None:
        client = _client()
        cohort = client.post(
            "/v1/cohorts", json={"name": "a4", "slot_count": 3}, headers=_h("key-alpha")
        ).json()
        cid = cohort["cohort_id"]
        client.post(f"/v1/cohorts/{cid}/cycles/run", headers=_h("key-alpha"))

        usage_a = client.get("/v1/admin/usage", headers=_h("key-alpha")).json()
        usage_b = client.get("/v1/admin/usage", headers=_h("key-beta")).json()
        assert cid in [u["cohort_id"] for u in usage_a["cohorts"]]
        assert cid not in [u["cohort_id"] for u in usage_b["cohorts"]]

    def test_webhooks_scoped_by_tenant(self) -> None:
        client = _client()
        client.post(
            "/v1/admin/webhooks",
            json={"url": "https://a.example/hook", "secret": "secret-aaaa"},
            headers=_h("key-alpha"),
        )
        hooks_a = client.get("/v1/admin/webhooks", headers=_h("key-alpha")).json()
        hooks_b = client.get("/v1/admin/webhooks", headers=_h("key-beta")).json()
        assert [h["url"] for h in hooks_a] == ["https://a.example/hook"]
        assert hooks_b == []
