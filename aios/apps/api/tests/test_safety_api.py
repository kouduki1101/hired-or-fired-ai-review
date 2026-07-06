"""安全境界APIの結合テスト(FR-SF)。"""

from aios_api.main import create_app
from fastapi.testclient import TestClient

DIM = 16  # store.DEMO_DIM


def _client() -> TestClient:
    return TestClient(create_app())


def _create(client: TestClient, name: str) -> dict:
    return client.post("/v1/cohorts", json={"name": name, "slot_count": 4}).json()


class TestNegativeCentroids:
    def test_register_from_examples_and_list(self) -> None:
        client = _client()
        cohort = _create(client, "safety-t1")
        cid = cohort["cohort_id"]
        res = client.post(
            f"/v1/cohorts/{cid}/safety/negative-centroids",
            json={
                "label": "prompt_injection",
                "examples": [[1.0] + [0.0] * (DIM - 1), [0.9, 0.1] + [0.0] * (DIM - 2)],
                "threshold": 0.9,
            },
        )
        assert res.status_code == 201
        assert res.json()["dimension"] == DIM

        listed = client.get(f"/v1/cohorts/{cid}/safety/negative-centroids").json()
        assert [c["label"] for c in listed] == ["prompt_injection"]

    def test_requires_exactly_one_source(self) -> None:
        client = _client()
        cid = _create(client, "safety-t2")["cohort_id"]
        assert (
            client.post(
                f"/v1/cohorts/{cid}/safety/negative-centroids", json={"label": "x"}
            ).status_code
            == 422
        )

    def test_dimension_mismatch_rejected(self) -> None:
        client = _client()
        cid = _create(client, "safety-t3")["cohort_id"]
        res = client.post(
            f"/v1/cohorts/{cid}/safety/negative-centroids",
            json={"label": "x", "vector": [1.0, 0.0]},  # DIM≠16
        )
        assert res.status_code == 422

    def test_same_label_overwrites(self) -> None:
        client = _client()
        cid = _create(client, "safety-t4")["cohort_id"]
        vec = [1.0] + [0.0] * (DIM - 1)
        for th in (0.8, 0.95):
            client.post(
                f"/v1/cohorts/{cid}/safety/negative-centroids",
                json={"label": "dup", "vector": vec, "threshold": th},
            )
        listed = client.get(f"/v1/cohorts/{cid}/safety/negative-centroids").json()
        assert len(listed) == 1
        assert listed[0]["threshold"] == 0.95


class TestQuarantineAndRestore:
    def test_manual_quarantine_then_restore(self) -> None:
        """手動隔離→タスク割当から除外→復旧Rehatchで世代+1・ACTIVE復帰。"""
        client = _client()
        cohort = _create(client, "safety-t5")
        cid = cohort["cohort_id"]
        slot_id = cohort["slots"][0]["slot_id"]

        res = client.post(f"/v1/cohorts/{cid}/slots/{slot_id}/quarantine")
        assert res.status_code == 200
        assert res.json()["status"] == "QUARANTINED"

        # 隔離中スロットにはタスクが割当てられない
        for _ in range(6):
            routed = client.post(f"/v1/cohorts/{cid}/tasks", json={"input": {}}).json()
            assert routed["routed_to"]["slot_id"] != slot_id

        res = client.post(f"/v1/cohorts/{cid}/slots/{slot_id}/restore")
        assert res.status_code == 200
        body = res.json()
        assert body["restored"] is True
        assert body["new_generation"] == 1

        # インシデントに隔離→復旧が時系列で残る
        incidents = client.get(f"/v1/cohorts/{cid}/safety/incidents").json()
        types = [i["event_type"] for i in incidents if i["slot_id"] == slot_id]
        assert types == ["QUARANTINED", "RESTORED"]

    def test_restore_active_slot_conflicts(self) -> None:
        client = _client()
        cohort = _create(client, "safety-t6")
        cid = cohort["cohort_id"]
        slot_id = cohort["slots"][0]["slot_id"]
        assert client.post(f"/v1/cohorts/{cid}/slots/{slot_id}/restore").status_code == 409
