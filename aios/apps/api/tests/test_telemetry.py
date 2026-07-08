"""OpenTelemetry 計装(NFR-OP)の検証。

グローバル TracerProvider に InMemorySpanExporter を挿し、
ドメインスパン(サイクル実行・タスクルーティング)と FastAPI サーバスパンが
生成されることを確認する。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from aios_api.main import create_app
from aios_api.telemetry import configure_telemetry, init_telemetry, instrument_app
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture(scope="module")
def exporter() -> InMemorySpanExporter:
    exp = InMemorySpanExporter()
    # グローバルプロバイダは一度だけ構成できる(モジュール内で共有)
    init_telemetry(span_exporter=exp)
    return exp


@pytest.fixture()
def client(exporter: InMemorySpanExporter) -> Iterator[TestClient]:
    app = create_app()
    instrument_app(app)
    exporter.clear()
    yield TestClient(app)
    exporter.clear()


def _span_names(exporter: InMemorySpanExporter) -> list[str]:
    return [s.name for s in exporter.get_finished_spans()]


def test_cycle_span_emitted(client: TestClient, exporter: InMemorySpanExporter) -> None:
    cohort = client.post("/v1/cohorts", json={"name": "otel", "slot_count": 4}).json()
    cid = cohort["cohort_id"]
    client.post(f"/v1/cohorts/{cid}/cycles/run")

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "aios.cycle.run" in spans
    cycle = spans["aios.cycle.run"]
    assert cycle.attributes["aios.cohort_id"] == cid
    assert cycle.attributes["aios.step_no"] == 1
    assert "aios.health" in cycle.attributes


def test_task_route_span_emitted(client: TestClient, exporter: InMemorySpanExporter) -> None:
    cohort = client.post("/v1/cohorts", json={"name": "otel2", "slot_count": 4}).json()
    cid = cohort["cohort_id"]
    client.post(
        f"/v1/cohorts/{cid}/tasks",
        json={"input": {"messages": []}, "metadata": {"importance": "high"}},
    )
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "aios.task.route" in spans
    assert spans["aios.task.route"].attributes["aios.importance"] == "high"


def test_fastapi_server_span_emitted(client: TestClient, exporter: InMemorySpanExporter) -> None:
    client.post("/v1/cohorts", json={"name": "otel3", "slot_count": 3})
    # FastAPI 自動計装が HTTP サーバスパンを生成する(ルートテンプレート名を含む)
    names = _span_names(exporter)
    assert any("/v1/cohorts" in n for n in names)


def test_configure_disabled_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIOS_OTEL_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("AIOS_OTEL_ENABLED", raising=False)
    assert configure_telemetry(create_app()) is False
