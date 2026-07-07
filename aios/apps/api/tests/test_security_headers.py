"""セキュリティヘッダ(多層防御、NFR-SE)の結合テスト。"""

from __future__ import annotations

from aios_api.main import create_app
from aios_api.security import SECURITY_HEADERS
from fastapi.testclient import TestClient


def test_security_headers_on_all_responses() -> None:
    client = TestClient(create_app())
    # 認証免除の死活エンドポイントでも付与される
    res = client.get("/healthz")
    for name, value in SECURITY_HEADERS.items():
        assert res.headers.get(name) == value


def test_security_headers_on_error_response() -> None:
    client = TestClient(create_app(api_keys={"k": "t"}))
    res = client.get("/v1/cohorts")  # 401(認証必須)
    assert res.status_code == 401
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert (
        res.headers.get("Content-Security-Policy")
        == "default-src 'none'; frame-ancestors 'none'"
    )
