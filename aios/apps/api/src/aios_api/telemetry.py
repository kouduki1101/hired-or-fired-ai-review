"""OpenTelemetry 可観測性の配線(NFR-OP-01: Trace + Metrics)。

- FastAPI 自動計装で HTTP サーバスパンを生成
- ドメイン操作(制御サイクル・タスクルーティング)に手動スパン + メトリクスを付与
- エクスポータは環境変数で選択:
    AIOS_OTEL_OTLP_ENDPOINT 設定時 → OTLP/HTTP(Trace=BatchSpanProcessor,
      Metrics=PeriodicExportingMetricReader)。ベース URL でも /v1/traces 付き URL でも可。
    未設定時 → プロバイダ未構成(スパン・計測は no-op、計装コストほぼゼロ)

`tracer` / 各メトリクス instrument はモジュール読込時に取得するプロキシで、
プロバイダ構成前に取得しても記録時に最新のグローバルプロバイダへ解決される。
テストは init_telemetry に InMemorySpanExporter / InMemoryMetricReader を渡して捕捉する。
"""

from __future__ import annotations

import os
from typing import Any

from opentelemetry import metrics, trace

_SERVICE_NAME = "aios-api"
_initialized = False

# プロバイダ構成前でも安全(プロキシ)。記録時にグローバルへ解決。
tracer = trace.get_tracer("aios.api")
_meter = metrics.get_meter("aios.api")

# メトリクス instrument(低カーディナリティ属性のみ付与する)
tasks_routed = _meter.create_counter("aios.tasks.routed", unit="1", description="routed tasks")
cycles_run = _meter.create_counter("aios.cycles.run", unit="1", description="control cycles run")
rehatches_committed = _meter.create_counter(
    "aios.rehatches.committed", unit="1", description="committed rehatches"
)
cycle_duration_ms = _meter.create_histogram(
    "aios.cycle.duration", unit="ms", description="control cycle wall time"
)
route_duration_ms = _meter.create_histogram(
    "aios.task.route.duration", unit="ms", description="task routing wall time"
)


def _signal_url(base: str, signal: str) -> str:
    """ベース URL / signal 付き URL のどちらからでも `.../v1/<signal>` を導く。"""
    for suffix in ("/v1/traces", "/v1/metrics", "/v1/logs"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base.rstrip('/')}/v1/{signal}"


def init_telemetry(
    *,
    span_exporter: Any | None = None,
    metric_reader: Any | None = None,
    otlp_endpoint: str | None = None,
    service_name: str = _SERVICE_NAME,
) -> bool:
    """グローバル Tracer/Meter プロバイダを(未設定なら)構成する。構成したら True。"""
    global _initialized
    if _initialized:
        return True
    if span_exporter is None and metric_reader is None and not otlp_endpoint:
        return False

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    resource = Resource.create({"service.name": service_name})

    # --- Traces ---
    tracer_provider = TracerProvider(resource=resource)
    if span_exporter is not None:
        tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    elif otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=_signal_url(otlp_endpoint, "traces")))
        )
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics ---
    from opentelemetry.sdk.metrics import MeterProvider

    readers = []
    if metric_reader is not None:
        readers.append(metric_reader)
    elif otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=_signal_url(otlp_endpoint, "metrics"))
            )
        )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))

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
