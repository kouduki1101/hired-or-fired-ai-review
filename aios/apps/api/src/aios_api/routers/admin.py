"""管理API: Webhookエンドポイント登録・配送記録(FR-EX-01 / docs/05 §3)。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, HttpUrl

from aios_api.notify import WebhookEndpoint
from aios_api.store import STORE

router = APIRouter(tags=["admin"])


class RegisterWebhookRequest(BaseModel):
    url: HttpUrl
    secret: str = Field(min_length=8, max_length=200)
    events: list[str] | None = None  # 未指定は全イベント購読


class WebhookResponse(BaseModel):
    url: str
    events: list[str] | None
    # secretは返さない(NFR-SE-04)


@router.post("/admin/webhooks", status_code=201, response_model=WebhookResponse)
async def register_webhook(req: RegisterWebhookRequest) -> WebhookResponse:
    from aios_api.auth import current_tenant

    STORE.notifier.register(
        WebhookEndpoint(
            url=str(req.url),
            secret=req.secret,
            events=frozenset(req.events) if req.events else None,
            tenant=current_tenant.get(),
        )
    )
    return WebhookResponse(url=str(req.url), events=req.events)


@router.get("/admin/webhooks", response_model=list[WebhookResponse])
async def list_webhooks() -> list[WebhookResponse]:
    from aios_api.auth import current_tenant

    tenant = current_tenant.get()
    return [
        WebhookResponse(url=e.url, events=sorted(e.events) if e.events else None)
        for e in STORE.notifier.list_endpoints()
        if e.tenant == tenant
    ]


@router.get("/admin/webhooks/deliveries")
async def list_deliveries(limit: int = 20) -> list[dict[str, Any]]:
    """直近の配送記録(デバッグ用)。"""
    return [
        {"event": d.event_type, "url": d.url, "status": d.status,
         "delivered_at": d.delivered_at}
        for d in STORE.notifier.deliveries[-max(1, min(limit, 100)):]
    ]


@router.get("/admin/usage")
async def usage_report() -> dict[str, Any]:
    """使用量メータリング(FR-TN-03): 課金基盤へのエクスポート元データ。"""
    items = STORE.usage()
    return {
        "cohorts": items,
        "totals": {
            key: sum(i[key] for i in items)
            for key in (
                "slot_count", "cycles_run", "tasks_processed",
                "probes_executed", "rehatches_committed",
            )
        },
    }
