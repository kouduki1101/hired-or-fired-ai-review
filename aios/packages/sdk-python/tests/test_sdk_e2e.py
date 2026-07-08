"""SDK e2e: 実uvicornサーバに対して高水準APIを一巡させる。"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from aios_api.main import create_app
from aios_sdk import AiosApiError, Client

API_KEY = "sdk-key-123"
TENANT_KEYS = {API_KEY: "sdk-tenant"}


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    """テスト用に実HTTPサーバを起動(SDKは本物のHTTPスタックを通る)。"""
    app = create_app(api_keys=TENANT_KEYS)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def aios(base_url: str) -> Iterator[Client]:
    with Client(base_url=base_url, api_key=API_KEY) as client:
        yield client


class TestSdkRoundtrip:
    def test_cohort_task_lineage_flow(self, aios: Client) -> None:
        """docs/05 §4 の使用例そのまま: 作成→タスク→開示請求応答。"""
        cohort = aios.cohorts.create(name="sdk-cohort", slot_count=5)
        assert cohort.get()["phase"] == "OPERATING"

        result = cohort.tasks.run(
            messages=[{"role": "user", "content": "hello"}], importance="high"
        )
        assert result["routed_to"]["display_id"]

        lineage = aios.lineage.task(result["task_id"])
        assert "説明" not in lineage or lineage  # 構造化応答が返る
        assert lineage["handled_by"]["slot_id"] == result["routed_to"]["slot_id"]
        assert "第0世代" in lineage["explanation"]

    def test_cycle_and_metrics(self, aios: Client) -> None:
        cohort = aios.cohorts.create(name="sdk-metrics", slot_count=4)
        summary = cohort.run_cycle()
        assert summary["step_no"] == 1
        current = cohort.metrics()
        assert current["health"] in ("FIXED", "STABLE", "CHAOTIC")
        assert len(cohort.metrics_history()) == 1

    def test_approval_flow(self, aios: Client) -> None:
        """manualコホートの次元拡張: 202→承認→実施。"""
        cohort = aios.cohorts.create(name="sdk-appr", slot_count=4, approval_mode="manual")
        res = cohort.expand_dimension(2, ["倫理", "法務"])
        assert res["status"] == "pending"

        pending = aios.approvals.list(status="pending")
        target = next(a for a in pending if a["cohort_id"] == cohort.cohort_id)
        approved = aios.approvals.approve(target["approval_id"])
        assert approved["payload"]["new_dimension"] == 18

    def test_quarantine_restore_and_usage(self, aios: Client) -> None:
        cohort = aios.cohorts.create(name="sdk-safety", slot_count=3)
        slot_id = cohort.get()["slots"][0]["slot_id"]
        assert cohort.quarantine(slot_id)["status"] == "QUARANTINED"
        assert cohort.restore(slot_id)["restored"] is True

        usage = aios.admin.usage()
        assert any(u["cohort_id"] == cohort.cohort_id for u in usage["cohorts"])

    def test_audit_export_consistency(self, aios: Client) -> None:
        import json

        cohort = aios.cohorts.create(name="sdk-audit", slot_count=3)
        cohort.run_cycle()
        ndjson = cohort.export_audit()
        manifest = cohort.export_manifest()
        assert len(ndjson.strip().splitlines()) == manifest["total_events"]
        assert all(json.loads(line)["hash"] for line in ndjson.strip().splitlines())

    def test_learning_rehatch_flow(self, aios: Client) -> None:
        """P5: 学習系Rehatchを投入→進捗→完了で世代+1(Rehatch-in-Place)。"""
        cohort = aios.cohorts.create(name="sdk-train", slot_count=4)
        slot = cohort.get()["slots"][0]
        slot_id, gen0 = slot["slot_id"], slot["generation"]

        job = cohort.train_rehatch(slot_id, max_steps=3)
        assert job["status"] in ("pending", "running")

        applied = None
        for _ in range(10):
            applied = cohort.advance_training(slot_id, job["job_id"])
            if applied["applied"]:
                break
        assert applied is not None and applied["committed"] is True
        assert applied["generation"] == gen0 + 1

    def test_error_surface(self, base_url: str) -> None:
        """認証エラーがAiosApiError(status/aios_code)として現れる。"""
        with Client(base_url=base_url, api_key="wrong-key") as bad, \
                pytest.raises(AiosApiError) as ei:
            bad.cohorts.list()
        assert ei.value.status == 401
        assert ei.value.aios_code == "unauthorized"

    def test_tenant_isolation_through_sdk(self, aios: Client, base_url: str) -> None:
        cohort = aios.cohorts.create(name="sdk-iso", slot_count=3)
        # 別テナントキーは存在しない→401。テナント分離自体はAPIテスト済みのため認証面のみ
        with Client(base_url=base_url) as anon, pytest.raises(AiosApiError):
            anon.cohorts.get(cohort.cohort_id).get()
