"""ガバナンスAPI結合テスト: リネージ照会・自律提案調停・ループ制御。"""

from aios_api.main import create_app
from fastapi.testclient import TestClient


def _client() -> TestClient:
    return TestClient(create_app())


def _setup(client: TestClient, name: str) -> tuple[dict, dict]:
    cohort = client.post("/v1/cohorts", json={"name": name, "slot_count": 5}).json()
    task = client.post(
        f"/v1/cohorts/{cohort['cohort_id']}/tasks",
        json={"input": {"messages": [{"role": "user", "content": "hello"}]}},
    ).json()
    return cohort, task


class TestTaskLineage:
    def test_disclosure_response(self) -> None:
        """開示請求応答(¶0224-0226): 担当スロット・世代・判断・制御値+説明文。"""
        client = _client()
        _, task = _setup(client, "lineage-t1")
        res = client.get(f"/v1/lineage/tasks/{task['task_id']}")
        assert res.status_code == 200
        body = res.json()
        assert body["handled_by"]["display_id"] == task["routed_to"]["display_id"]
        assert body["handled_by"]["generation"] == 0
        assert body["generation_lineage"]["strategy"] is None  # 第0世代=卵層生成
        assert "スロット" in body["explanation"]
        assert "第0世代" in body["explanation"]

    def test_unknown_task_404(self) -> None:
        assert _client().get("/v1/lineage/tasks/nonexistent").status_code == 404


class TestSlotHistory:
    def test_timeline_with_chain_verification(self) -> None:
        """運用履歴タイムライン: 全イベント+ハッシュチェーン検証(FR-GV-03)。"""
        client = _client()
        cohort, task = _setup(client, "history-t1")
        slot_id = task["routed_to"]["slot_id"]
        res = client.get(f"/v1/lineage/slots/{slot_id}/history")
        assert res.status_code == 200
        body = res.json()
        assert body["chain_verified"] is True
        types = [e["event_type"] for e in body["events"]]
        assert types[0] == "SLOT_CREATED"
        assert "TASK_ASSIGNED" in types and "TASK_COMPLETED" in types
        assert all(len(e["hash"]) == 64 for e in body["events"])  # SHA-256 hex


class TestProposals:
    def test_rehatch_request_arbitrated_and_recorded(self) -> None:
        """自律提案が群状態と照合して判定され、履歴に記録される(¶0228-0230)。"""
        client = _client()
        cohort, _ = _setup(client, "proposal-t1")
        client.post(f"/v1/cohorts/{cohort['cohort_id']}/cycles/run")  # 健全性を観測

        slot_id = cohort["slots"][0]["slot_id"]
        res = client.post(
            "/v1/proposals",
            json={
                "slot_id": slot_id,
                "kind": "rehatch_request",
                "rationale": {"val_loss_plateau_cycles": 12},
            },
        )
        assert res.status_code == 201
        body = res.json()
        assert body["decision"] in ("approved", "rejected")
        assert body["cohort_health"] in ("FIXED", "STABLE", "CHAOTIC")

        # 提出と判定が運用履歴に残る
        history = client.get(f"/v1/lineage/slots/{slot_id}/history").json()
        types = [e["event_type"] for e in history["events"]]
        assert "PROPOSAL_SUBMITTED" in types and "PROPOSAL_DECIDED" in types

    def test_unobserved_cohort_holds_decision(self) -> None:
        """未観測(サイクル未実行)の群では判定保留=否認。"""
        client = _client()
        cohort, _ = _setup(client, "proposal-t2")
        slot_id = cohort["slots"][0]["slot_id"]
        res = client.post("/v1/proposals", json={"slot_id": slot_id, "kind": "rehatch_request"})
        body = res.json()
        assert body["decision"] == "rejected"
        assert body["rule"] == "no_observation"

    def test_locked_slot_rejected(self) -> None:
        client = _client()
        cohort, _ = _setup(client, "proposal-t3")
        client.post(f"/v1/cohorts/{cohort['cohort_id']}/cycles/run")
        slot_id = cohort["slots"][0]["slot_id"]
        client.put(
            f"/v1/cohorts/{cohort['cohort_id']}/slots/{slot_id}/lock",
            json={"rehatch_lock": True},
        )
        res = client.post("/v1/proposals", json={"slot_id": slot_id, "kind": "rehatch_request"})
        assert res.json()["rule"] == "slot_locked"


class TestLoopControl:
    def test_pause_blocks_cycles(self) -> None:
        client = _client()
        cohort, _ = _setup(client, "loop-t1")
        cid = cohort["cohort_id"]
        assert client.post(f"/v1/cohorts/{cid}/loop", json={"action": "pause"}).status_code == 200
        assert client.post(f"/v1/cohorts/{cid}/cycles/run").status_code == 409  # PAUSED
        client.post(f"/v1/cohorts/{cid}/loop", json={"action": "resume"})
        assert client.post(f"/v1/cohorts/{cid}/cycles/run").status_code == 200

    def test_dry_run_mode_forces_decision_only(self) -> None:
        client = _client()
        cohort, _ = _setup(client, "loop-t2")
        cid = cohort["cohort_id"]
        client.post(f"/v1/cohorts/{cid}/loop", json={"action": "dry_run_on"})
        res = client.post(f"/v1/cohorts/{cid}/cycles/run")
        assert res.json()["dry_run"] is True

    def test_unknown_action_422(self) -> None:
        client = _client()
        cohort, _ = _setup(client, "loop-t3")
        res = client.post(
            f"/v1/cohorts/{cohort['cohort_id']}/loop", json={"action": "explode"}
        )
        assert res.status_code == 422
