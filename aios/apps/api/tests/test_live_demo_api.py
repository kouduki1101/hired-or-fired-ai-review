"""APIレベルの結合テスト: 卵層→タスクルーティング→制御サイクルの一気通貫。"""

from aios_api.main import create_app
from fastapi.testclient import TestClient


def _client() -> TestClient:
    return TestClient(create_app())


def _create(client: TestClient, name: str, k: int = 6) -> dict:
    res = client.post("/v1/cohorts", json={"name": name, "slot_count": k})
    assert res.status_code == 201
    return res.json()


class TestTaskRouting:
    def test_task_routed_and_lineage_returned(self) -> None:
        client = _client()
        cohort = _create(client, "routing-test")
        res = client.post(
            f"/v1/cohorts/{cohort['cohort_id']}/tasks",
            json={"input": {"messages": [{"role": "user", "content": "hello"}]}},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["routed_to"]["slot_id"] in {s["slot_id"] for s in cohort["slots"]}
        assert body["routed_to"]["generation"] == 0
        assert body["routing_reason"]

    def test_maturity_grows_with_tasks(self) -> None:
        client = _client()
        cohort = _create(client, "maturity-test")
        for _ in range(5):
            client.post(f"/v1/cohorts/{cohort['cohort_id']}/tasks", json={"input": {}})
        after = client.get(f"/v1/cohorts/{cohort['cohort_id']}").json()
        assert sum(s["maturity"] for s in after["slots"]) == 5


class TestControlCycle:
    def test_cycle_computes_metrics(self) -> None:
        """制御サイクル1周で散逸度・健全性・適合度が算出される(図10)。"""
        client = _client()
        cohort = _create(client, "cycle-test")
        res = client.post(f"/v1/cohorts/{cohort['cohort_id']}/cycles/run")
        assert res.status_code == 200
        body = res.json()
        assert body["step_no"] == 1
        assert body["health"] in ("FIXED", "STABLE", "CHAOTIC")
        assert body["dissipation"] is not None and body["dissipation"] >= 0.0

        current = client.get(f"/v1/cohorts/{cohort['cohort_id']}/metrics/current").json()
        assert current["step_no"] == 1
        assert current["last_cycle"]["health"] == body["health"]

    def test_dry_run_does_not_actuate(self) -> None:
        client = _client()
        cohort = _create(client, "dryrun-test")
        res = client.post(f"/v1/cohorts/{cohort['cohort_id']}/cycles/run?dry_run=true")
        assert res.status_code == 200
        assert res.json()["dry_run"] is True
        after = client.get(f"/v1/cohorts/{cohort['cohort_id']}").json()
        assert all(s["generation"] == 0 for s in after["slots"])  # 作用なし

    def test_fitness_visible_after_cycle(self) -> None:
        client = _client()
        cohort = _create(client, "fitness-test")
        client.post(f"/v1/cohorts/{cohort['cohort_id']}/cycles/run")
        after = client.get(f"/v1/cohorts/{cohort['cohort_id']}").json()
        assert all(s["fitness"] is not None for s in after["slots"])


class TestMetricsHistory:
    def test_history_accumulates_cycles(self) -> None:
        """FR-UI-03: サイクル時系列がスロット別適合度込みで取得できる。"""
        client = _client()
        cohort = _create(client, "history-metrics-test")
        cid = cohort["cohort_id"]
        for _ in range(3):
            client.post(f"/v1/cohorts/{cid}/cycles/run")
        res = client.get(f"/v1/cohorts/{cid}/metrics/history")
        assert res.status_code == 200
        body = res.json()
        assert [h["step_no"] for h in body] == [1, 2, 3]
        assert all(len(h["slots"]) == 6 for h in body)
        assert body[-1]["health"] in ("FIXED", "STABLE", "CHAOTIC")

    def test_current_includes_loop_state(self) -> None:
        client = _client()
        cohort = _create(client, "loopstate-test")
        cid = cohort["cohort_id"]
        current = client.get(f"/v1/cohorts/{cid}/metrics/current").json()
        assert current["loop_state"] == "RUNNING"
        client.post(f"/v1/cohorts/{cid}/loop", json={"action": "pause"})
        current = client.get(f"/v1/cohorts/{cid}/metrics/current").json()
        assert current["loop_state"] == "PAUSED"
