"""OpenTelemetry 可観測性の配線(NFR-OP: 可観測性)。

- FastAPI 自動計装で HTTP サーバスパンを生成
- ドメイン操作(制御サイクル・タスクルーティング)に手動スパンを付与
- エクスポータは環境変数で選択:
    AIOS_OTEL_OTLP_ENDPOINT 設定時 → OTLP/HTTP(BatchSpanProcessor)
    未設定時 → プロバイダ未構成(スパンは no-op、計装コストほぼゼロ)

`tracer` はモジュール読込時に取得するプロキシで、プロバイダ構成前に取得しても
スパン生成時に最新のグローバルプロバイダへ解決される。テストは init_telemetry に
InMemorySpanExporter を渡してスパンを捕捉する。
"""

from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace

_SERVICE_NAME = "aios-api"
_initialized = False

# プロバイダ構成前でも安全(プロキシ)。スパン生成時にグローバルへ解決。
tracer = trace.get_tracer("aios.api")


def init_telemetry(
    *,
    span_exporter: Any | None = None,
    otlp_endpoint: str | None = None,
    service_name: str = _SERVICE_NAME,
) -> bool:
    """グローバル TracerProvider を(未設定なら)構成する。構成したら True。"""
    global _initialized
    if _initialized:
        return True

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if span_exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    elif otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    else:
        return False

    trace.set_tracer_provider(provider)
    _initialized = True
    return True


def instrument_app(app: Any) -> None:
    """FastAPI アプリを自動計装する(HTTP サーバスパン)。"""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


def configure_telemetry(app: Any) -> bool:
    """環境変数に基づき計装を有効化する。有効化したら True。"""
    endpoint = os.environ.get("AIOS_OTEL_OTLP_ENDPOINT")
    if not endpoint and os.environ.get("AIOS_OTEL_ENABLED") != "1":
        return False
    init_telemetry(otlp_endpoint=endpoint)
    instrument_app(app)
    return True
