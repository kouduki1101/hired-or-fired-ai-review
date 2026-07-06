"""承認ワークフロー(FR-GV-05)と使用量メータリング(FR-TN-03)の結合テスト。"""

from __future__ import annotations

from aios_api.main import create_app
from aios_api.store import STORE
from fastapi.testclient import TestClient


def _client() -> TestClient:
    return TestClient(create_app())


def _create(client: TestClient, name: str, mode: str = "manual", k: int = 6) -> dict:
    return client.post(
        "/v1/cohorts",
        json={"name": name, "slot_count": k, "approval_mode": mode},
    ).json()


def _force_deviant(cohort_id: str, index: int = 0) -> str:
    """テスト補助: スロットを教師ベクトル逆方向へ逸脱させ、Rehatch選定対象にする。"""
    cohort = STORE.get_cohort(cohort_id)
    slot = cohort.slots[index]
    slot.adapter.force_behavior(-cohort.teacher_vector)  # type: ignore[attr-defined]
    return slot.slot_id


class TestRehatchApproval:
    def test_manual_mode_defers_rehatch_to_queue(self) -> None:
        """manualモード: 選定はされるが実行されず、承認キューに積まれる。"""
        client = _client()
        cohort = _create(client, "appr-t1")
        cid = cohort["cohort_id"]
        client.post(f"/v1/cohorts/{cid}/cycles/run")
        deviant_id = _force_deviant(cid)

        pending_seen = False
        for _ in range(5):
            r = client.post(f"/v1/cohorts/{cid}/cycles/run").json()
            if any(p["slot_id"] == deviant_id for p in r["pending_rehatch"]):
                pending_seen = True
                break
        assert pending_seen, "承認モードでRehatch選定がpendingにならなかった"

        # 実行されていない(世代0のまま)
        slots = client.get(f"/v1/cohorts/{cid}").json()["slots"]
        deviant = next(s for s in slots if s["slot_id"] == deviant_id)
        assert deviant["generation"] == 0

        # キューに載っている
        pending = client.get("/v1/approvals?status=pending").json()
        assert any(
            a["action_type"] == "rehatch" and a["payload"]["slot_id"] == deviant_id
            for a in pending
        )

    def test_approve_executes_rehatch(self) -> None:
        """承認→Rehatch実行(世代+1)、選定イベント+完了イベントが履歴に残る。"""
        client = _client()
        cohort = _create(client, "appr-t2")
        cid = cohort["cohort_id"]
        client.post(f"/v1/cohorts/{cid}/cycles/run")
        deviant_id = _force_deviant(cid)
        for _ in range(5):
            client.post(f"/v1/cohorts/{cid}/cycles/run")

        pending = [
            a for a in client.get("/v1/approvals?status=pending").json()
            if a["cohort_id"] == cid and a["payload"]["slot_id"] == deviant_id
        ]
        assert pending
        res = client.post(f"/v1/approvals/{pending[0]['approval_id']}/approve", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "approved"
        assert body["payload"]["committed"] is True
        assert body["payload"]["new_generation"] == 1

        history = client.get(f"/v1/lineage/slots/{deviant_id}/history").json()
        types = [e["event_type"] for e in history["events"]]
        assert "REHATCH_SELECTED" in types  # 承認前の選定も監査に残る
        assert "REHATCH_COMPLETED" in types

    def test_reject_leaves_slot_untouched(self) -> None:
        client = _client()
        cohort = _create(client, "appr-t3")
        cid = cohort["cohort_id"]
        client.post(f"/v1/cohorts/{cid}/cycles/run")
        deviant_id = _force_deviant(cid)
        for _ in range(5):
            client.post(f"/v1/cohorts/{cid}/cycles/run")

        pending = [
            a for a in client.get("/v1/approvals?status=pending").json()
            if a["cohort_id"] == cid
        ]
        res = client.post(
            f"/v1/approvals/{pending[0]['approval_id']}/reject",
            json={"comment": "今週は変更凍結期間"},
        )
        assert res.json()["status"] == "rejected"
        slots = client.get(f"/v1/cohorts/{cid}").json()["slots"]
        deviant = next(s for s in slots if s["slot_id"] == deviant_id)
        assert deviant["generation"] == 0  # 実行されていない

    def test_double_decision_conflicts(self) -> None:
        client = _client()
        cohort = _create(client, "appr-t4")
        cid = cohort["cohort_id"]
        approval_id = STORE.add_approval(
            cohort_id=cid, action_type="rehatch",
            payload={"slot_id": cohort["slots"][0]["slot_id"], "reason": "MANUAL"},
        )
        client.post(f"/v1/approvals/{approval_id}/reject", json={})
        assert client.post(f"/v1/approvals/{approval_id}/approve", json={}).status_code == 409


class TestExpansionApproval:
    def test_expand_gated_then_approved(self) -> None:
        """manualモードの次元拡張は202→承認後に実施される。"""
        client = _client()
        cohort = _create(client, "appr-t5", k=4)
        cid = cohort["cohort_id"]

        res = client.post(
            f"/v1/cohorts/{cid}/scaling/expand",
            json={"added_dims": 2, "axis_labels": ["倫理", "法務"]},
        )
        assert res.status_code == 202
        approval_id = res.json()["approval_id"]

        # まだ拡張されていない
        assert client.get(f"/v1/cohorts/{cid}/scaling/axes").json()["dimension"] == 16

        approved = client.post(f"/v1/approvals/{approval_id}/approve", json={}).json()
        assert approved["payload"]["new_dimension"] == 18
        axes = client.get(f"/v1/cohorts/{cid}/scaling/axes").json()
        assert axes["dimension"] == 18
        assert [a["label"] for a in axes["axes"]] == ["倫理", "法務"]

    def test_auto_mode_bypasses_queue(self) -> None:
        client = _client()
        cohort = _create(client, "appr-t6", mode="auto", k=4)
        cid = cohort["cohort_id"]
        res = client.post(
            f"/v1/cohorts/{cid}/scaling/expand",
            json={"added_dims": 1, "axis_labels": ["x"]},
        )
        assert res.status_code == 200  # 即時実行


class TestUsageMetering:
    def test_counters_reflect_operations(self) -> None:
        client = _client()
        cohort = _create(client, "usage-t1", mode="auto", k=5)
        cid = cohort["cohort_id"]
        for _ in range(3):
            client.post(f"/v1/cohorts/{cid}/cycles/run")
        for _ in range(4):
            client.post(f"/v1/cohorts/{cid}/tasks", json={"input": {}})
        client.post(f"/v1/cohorts/{cid}/cycles/run?dry_run=true")  # dry-runは非課金

        usage = client.get("/v1/admin/usage").json()
        row = next(u for u in usage["cohorts"] if u["cohort_id"] == cid)
        assert row["slot_count"] == 5
        assert row["cycles_run"] == 3
        assert row["tasks_processed"] == 4
        assert row["probes_executed"] == 15  # 5スロット×3サイクル
        assert usage["totals"]["tasks_processed"] >= 4


class TestApprovalDedup:
    def test_repeated_selection_does_not_duplicate_queue(self) -> None:
        """サイクル毎に同一スロットが再選定されてもキューは1件のまま。"""
        client = _client()
        cohort = _create(client, "appr-dedup")
        cid = cohort["cohort_id"]
        client.post(f"/v1/cohorts/{cid}/cycles/run")
        deviant_id = _force_deviant(cid)
        for _ in range(6):
            client.post(f"/v1/cohorts/{cid}/cycles/run")
        pending = [
            a for a in client.get("/v1/approvals?status=pending").json()
            if a["cohort_id"] == cid and a["payload"].get("slot_id") == deviant_id
        ]
        assert len(pending) == 1
