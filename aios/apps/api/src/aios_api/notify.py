"""Webhook通知(FR-EX-01 / docs/05 §3)。

- HMAC-SHA256署名: X-AIOS-Signature: sha256=<hex(HMAC(secret, body))>
- 対象イベント: cohort.health_changed / slot.quarantined / rehatch.completed /
  rehatch.rolled_back / cohort.stabilization_point / dynamics.adjusted
- P2は即時1回配送+配送記録(指数バックオフ24hリトライはP4のNotifyWorkerで実装)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from aios_orchestrator.cycle import CycleResult


@dataclass(frozen=True)
class WebhookEndpoint:
    url: str
    secret: str
    events: frozenset[str] | None = None  # Noneは全イベント購読


@dataclass
class Delivery:
    event_type: str
    url: str
    status: int | None  # Noneは接続失敗
    payload: dict[str, Any]
    delivered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def sign_payload(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class Notifier:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._endpoints: list[WebhookEndpoint] = []
        self.deliveries: list[Delivery] = []  # 直近の配送記録(デバッグ・テスト用)

    def register(self, endpoint: WebhookEndpoint) -> None:
        # 同一URLは上書き
        self._endpoints = [e for e in self._endpoints if e.url != endpoint.url]
        self._endpoints.append(endpoint)

    def list_endpoints(self) -> list[WebhookEndpoint]:
        return list(self._endpoints)

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        targets = [
            e for e in self._endpoints if e.events is None or event_type in e.events
        ]
        if not targets:
            return
        payload = {
            "event": event_type,
            "data": data,
            "emitted_at": datetime.now(UTC).isoformat(),
        }
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
            for ep in targets:
                status: int | None = None
                try:
                    res = await client.post(
                        ep.url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-AIOS-Signature": sign_payload(ep.secret, body),
                            "X-AIOS-Event": event_type,
                        },
                    )
                    status = res.status_code
                except httpx.HTTPError:
                    status = None  # 配送失敗を記録(P4でリトライキューへ)
                self.deliveries.append(
                    Delivery(event_type=event_type, url=ep.url, status=status, payload=payload)
                )
        del self.deliveries[:-100]

    async def emit_from_cycle(
        self, cohort_id: str, previous_health: str | None, result: CycleResult
    ) -> None:
        """CycleResultから通知イベントを導出して配送する。"""
        health = str(result.health)
        if previous_health is not None and health != previous_health:
            await self.emit(
                "cohort.health_changed",
                {"cohort_id": cohort_id, "from": previous_health, "to": health,
                 "dissipation": None if result.dissipation != result.dissipation
                 else result.dissipation},
            )
        for q in result.quarantined:
            await self.emit(
                "slot.quarantined",
                {"cohort_id": cohort_id, "slot_id": q.slot_id,
                 "label": q.label, "similarity": q.similarity},
            )
        for o in result.rehatched:
            await self.emit(
                "rehatch.completed" if o.committed else "rehatch.rolled_back",
                {"cohort_id": cohort_id, "slot_id": o.slot_id,
                 "reason": o.reason, "generation": o.new_generation},
            )
        if result.stabilization_point:
            await self.emit(
                "cohort.stabilization_point",
                {"cohort_id": cohort_id, "step_no": result.step_no},
            )
