"""AIOS Control Plane API(P0骨格)。

P0時点はインメモリストア。P1でpackages/storage(PostgreSQL)に置換する。
契約(スロット削除APIの不存在、Phase2でのスロット追加409)はこの時点から固定し、
apps/api/tests/contract で恒常的に回帰する。
"""

from __future__ import annotations

from aios_common.errors import AiosError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aios_api.routers import cohorts, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="AIOS Control Plane API",
        version="0.1.0",
        description="マルチエージェント群 長期運用基盤(特願2026-000860 実施品)",
    )
    app.include_router(health.router)
    app.include_router(cohorts.router, prefix="/v1")

    @app.exception_handler(AiosError)
    async def aios_error_handler(_: Request, exc: AiosError) -> JSONResponse:
        # RFC 9457 Problem Details(docs/05 §5)
        return JSONResponse(
            status_code=exc.status,
            content={
                "type": f"https://docs.aios.example/errors/{exc.code}",
                "title": exc.code,
                "detail": str(exc),
                "aios_code": exc.code,
            },
            media_type="application/problem+json",
        )

    return app


app = create_app()
