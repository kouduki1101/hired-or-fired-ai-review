"""レート制限(API4)と Webhook SSRF ガード(API7)の結合/単体テスト。"""

from __future__ import annotations

import pytest
from aios_api.main import create_app
from aios_api.netguard import validate_webhook_url
from aios_api.ratelimit import RateLimitConfig, TokenBucketLimiter
from aios_common.errors import InvalidWebhookUrlError
from fastapi.testclient import TestClient

KEYS = {"key-a": "tenant-a", "key-b": "tenant-b"}


class TestRateLimit:
    def test_limiter_token_bucket(self) -> None:
        lim = TokenBucketLimiter(RateLimitConfig(rps=1.0, burst=2))
        assert lim.allow("t", now=0.0)[0] is True   # 2 -> 1
        assert lim.allow("t", now=0.0)[0] is True   # 1 -> 0
        ok, retry = lim.allow("t", now=0.0)         # 0 -> 拒否
        assert ok is False and retry > 0
        # 1秒後に1トークン補充
        assert lim.allow("t", now=1.0)[0] is True

    def test_limiter_isolates_tenants(self) -> None:
        lim = TokenBucketLimiter(RateLimitConfig(rps=1.0, burst=1))
        assert lim.allow("a", now=0.0)[0] is True
        assert lim.allow("a", now=0.0)[0] is False
        # 別テナントは独立
        assert lim.allow("b", now=0.0)[0] is True

    def test_429_on_burst_exhaustion(self) -> None:
        app = create_app(api_keys=KEYS, rate_limit=RateLimitConfig(rps=1.0, burst=3))
        client = TestClient(app)
        h = {"X-API-Key": "key-a"}
        codes = [client.get("/v1/cohorts", headers=h).status_code for _ in range(6)]
        assert codes[:3] == [200, 200, 200]
        assert 429 in codes[3:]
        res = client.get("/v1/cohorts", headers=h)
        if res.status_code == 429:
            assert res.json()["aios_code"] == "rate_limited"
            assert int(res.headers["Retry-After"]) >= 1

    def test_healthz_not_rate_limited(self) -> None:
        app = create_app(api_keys=KEYS, rate_limit=RateLimitConfig(rps=1.0, burst=1))
        client = TestClient(app)
        # 死活監視は上限に関わらず常に 200
        for _ in range(5):
            assert client.get("/healthz").status_code == 200


class TestWebhookSsrfGuard:
    def _fake_resolver(self, mapping: dict[str, list[str]]):
        def resolve(host: str) -> list[str]:
            return mapping.get(host, ["93.184.216.34"])  # 既定は公開IP
        return resolve

    def test_blocks_ip_literal_metadata(self) -> None:
        with pytest.raises(InvalidWebhookUrlError):
            validate_webhook_url("http://169.254.169.254/latest/meta-data", allow_http=True)

    def test_blocks_loopback_and_private(self) -> None:
        for url in ("https://127.0.0.1/h", "https://10.0.0.5/h", "https://192.168.1.1/h"):
            with pytest.raises(InvalidWebhookUrlError):
                validate_webhook_url(url)

    def test_blocks_resolved_private(self) -> None:
        r = self._fake_resolver({"internal.corp": ["10.1.2.3"]})
        with pytest.raises(InvalidWebhookUrlError):
            validate_webhook_url("https://internal.corp/hook", resolver=r)

    def test_allows_public_resolved(self) -> None:
        r = self._fake_resolver({"hooks.example.com": ["93.184.216.34"]})
        validate_webhook_url("https://hooks.example.com/hook", resolver=r)  # 例外なし

    def test_requires_https_by_default(self) -> None:
        with pytest.raises(InvalidWebhookUrlError):
            validate_webhook_url("http://93.184.216.34/hook")  # allow_http 既定 False

    def test_allowlist_enforced(self) -> None:
        r = self._fake_resolver({"evil.example": ["93.184.216.34"]})
        with pytest.raises(InvalidWebhookUrlError):
            validate_webhook_url(
                "https://evil.example/hook",
                allowed_hosts=frozenset({"trusted.example"}),
                resolver=r,
            )
        # 許可ホストのサブドメインは通す
        validate_webhook_url(
            "https://api.trusted.example/hook",
            allowed_hosts=frozenset({"trusted.example"}),
            resolver=self._fake_resolver({"api.trusted.example": ["93.184.216.34"]}),
        )

    def test_register_webhook_rejects_private_ip(self) -> None:
        client = TestClient(create_app(api_keys=KEYS))
        res = client.post(
            "/v1/admin/webhooks",
            json={"url": "https://127.0.0.1/hook", "secret": "secret-aaaa"},
            headers={"X-API-Key": "key-a"},
        )
        assert res.status_code == 422
        assert res.json()["aios_code"] == "invalid_webhook_url"
