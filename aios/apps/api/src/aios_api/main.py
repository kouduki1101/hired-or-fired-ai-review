"""AIOS Control Plane API(P0骨格)。

P0時点はインメモリストア。P1でpackages/storage(PostgreSQL)に置換する。
契約(スロット削除APIの不存在、Phase2でのスロット追加409)はこの時点から固定し、
apps/api/tests/contract で恒常的に回帰する。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from aios_common.errors import AiosError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aios_api.oidc import OidcConfig
from aios_api.routers import (
    admin,
    approvals,
    cohorts,
    health,
    lineage,
    metrics,
    proposals,
    safety,
    scaling,
    tasks,
)
from aios_api.security import SecurityHeadersMiddleware


def create_app(
    database_url: str | None = None,
    api_keys: dict[str, str] | None = None,
    oidc: OidcConfig | None = None,
) -> FastAPI:
    """database_url(またはAIOS_DATABASE_URL)指定時は永続化が有効になり、
    起動時にDBから全コホートをrehydrateする(NFR-AV-03)。
    api_keys(またはAIOS_API_KEYS="key:tenant,...")指定時はAPIキー認証+
    テナント分離が有効になる(FR-TN-01/02)。
    oidc(またはAIOS_OIDC_ISSUER/AUDIENCE 環境変数)指定時は OIDC Bearer 認証+
    RBAC が有効になる(FR-TN-02 / NFR-SE-05)。"""
    from aios_api.auth import AuthMiddleware, resolve_api_keys

    url = database_url or os.environ.get("AIOS_DATABASE_URL")
    resolved_keys = resolve_api_keys(api_keys)
    resolved_oidc = oidc if oidc is not None else OidcConfig.from_env()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        engine = None
        if url:
            from aios_storage.schema import create_all
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

            from aios_api.store import STORE

            engine = create_async_engine(url)
            await create_all(engine)
            STORE.attach_db(async_sessionmaker(engine, expire_on_commit=False))
            await STORE.rehydrate_all()
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(
        title="AIOS Control Plane API",
        version="0.1.0",
        description="マルチエージェント群 長期運用基盤(特願2026-000860 実施品)",
        lifespan=lifespan,
    )
    app.include_router(admin.router, prefix="/v1")
    # 認証→CORSの順でadd(後がouter): CORSプリフライトは認証より先に処理される
    app.add_middleware(AuthMiddleware, api_keys=resolved_keys, oidc=resolved_oidc)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("AIOS_CORS_ORIGINS", "http://localhost:3000").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 最外層: 全レスポンス(エラー含む)にセキュリティヘッダを付与(多層防御)
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(health.router)
    app.include_router(cohorts.router, prefix="/v1")
    app.include_router(tasks.router, prefix="/v1")
    app.include_router(metrics.router, prefix="/v1")
    app.include_router(lineage.router, prefix="/v1")
    app.include_router(proposals.router, prefix="/v1")
    app.include_router(safety.router, prefix="/v1")
    app.include_router(scaling.router, prefix="/v1")
    app.include_router(approvals.router, prefix="/v1")

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
