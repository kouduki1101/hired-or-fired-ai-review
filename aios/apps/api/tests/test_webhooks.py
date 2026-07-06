"""Webhook通知(FR-EX-01): HMAC署名・イベント導出・API結合。"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
from aios_api.main import create_app
from aios_api.notify import Notifier, WebhookEndpoint, sign_payload
from aios_api.store import STORE
from aios_core.types import HealthStatus
from aios_orchestrator.cycle import CycleResult, QuarantineOutcome, RehatchOutcome
from fastapi.testclient import TestClient

SECRET = "test-secret-123"


def make_receiver() -> tuple[list[httpx.Request], httpx.MockTransport]:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    return received, httpx.MockTransport(handler)


def cycle_result(**kw) -> CycleResult:
    defaults = dict(
        step_no=5,
        health=HealthStatus.STABLE,
        dissipation=0.4,
        tv_drift=0.01,
        fitness_mean=0.8,
        lr_correction=1.0,
        noise_amount=0.05,
        rehatched=[],
        quarantined=[],
        stabilization_point=False,
        probe_missing=0,
        dry_run=False,
    )
    return CycleResult(**{**defaults, **kw})


class TestNotifier:
    async def test_signature_is_valid_hmac(self) -> None:
        received, transport = make_receiver()
        n = Notifier(transport=transport)
        n.register(WebhookEndpoint(url="https://hook.example/x", secret=SECRET))

        await n.emit("cohort.health_changed", {"from": "STABLE", "to": "FIXED"})

        assert len(received) == 1
        req = received[0]
        expected = "sha256=" + hmac.new(SECRET.encode(), req.content, hashlib.sha256).hexdigest()
        assert req.headers["X-AIOS-Signature"] == expected
        assert req.headers["X-AIOS-Event"] == "cohort.health_changed"
        body = json.loads(req.content)
        assert body["event"] == "cohort.health_changed"
        assert body["data"]["to"] == "FIXED"

    async def test_event_filter(self) -> None:
        received, transport = make_receiver()
        n = Notifier(transport=transport)
        n.register(
            WebhookEndpoint(
                url="https://hook.example/x",
                secret=SECRET,
                events=frozenset({"slot.quarantined"}),
            )
        )
        await n.emit("cohort.health_changed", {})
        await n.emit("slot.quarantined", {"slot_id": "s1"})
        assert [json.loads(r.content)["event"] for r in received] == ["slot.quarantined"]

    async def test_emit_from_cycle_derives_events(self) -> None:
        received, transport = make_receiver()
        n = Notifier(transport=transport)
        n.register(WebhookEndpoint(url="https://hook.example/x", secret=SECRET))

        result = cycle_result(
            health=HealthStatus.FIXED,
            rehatched=[RehatchOutcome("s1", "LOW_FITNESS", True, 2)],
            quarantined=[QuarantineOutcome("s2", "prompt_injection", 0.95)],
            stabilization_point=True,
        )
        await n.emit_from_cycle("c1", "STABLE", result)

        events = [json.loads(r.content)["event"] for r in received]
        assert events == [
            "cohort.health_changed",
            "slot.quarantined",
            "rehatch.completed",
            "cohort.stabilization_point",
        ]

    async def test_no_health_event_without_previous(self) -> None:
        received, transport = make_receiver()
        n = Notifier(transport=transport)
        n.register(WebhookEndpoint(url="https://hook.example/x", secret=SECRET))
        await n.emit_from_cycle("c1", None, cycle_result())
        assert received == []

    async def test_delivery_failure_recorded(self) -> None:
        def failing(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        n = Notifier(transport=httpx.MockTransport(failing))
        n.register(WebhookEndpoint(url="https://down.example/x", secret=SECRET))
        await n.emit("slot.quarantined", {})  # 例外を漏らさない
        assert n.deliveries[-1].status is None

    def test_sign_payload_roundtrip(self) -> None:
        body = b'{"a":1}'
        assert sign_payload(SECRET, body).startswith("sha256=")


class TestWebhookApi:
    def test_register_and_deliver_on_quarantine(self) -> None:
        """API結合: 登録→手動隔離→署名付き配送が記録される。"""
        client = TestClient(create_app())
        received, transport = make_receiver()
        STORE.notifier = Notifier(transport=transport)

        res = client.post(
            "/v1/admin/webhooks",
            json={"url": "https://hook.example/aios", "secret": SECRET},
        )
        assert res.status_code == 201
        assert "secret" not in res.json()  # シークレット非開示(NFR-SE-04)

        cohort = client.post("/v1/cohorts", json={"name": "wh-test", "slot_count": 3}).json()
        slot_id = cohort["slots"][0]["slot_id"]
        client.post(f"/v1/cohorts/{cohort['cohort_id']}/slots/{slot_id}/quarantine")

        events = [json.loads(r.content)["event"] for r in received]
        assert "slot.quarantined" in events

        deliveries = client.get("/v1/admin/webhooks/deliveries").json()
        assert deliveries[-1]["event"] == "slot.quarantined"
        assert deliveries[-1]["status"] == 200
