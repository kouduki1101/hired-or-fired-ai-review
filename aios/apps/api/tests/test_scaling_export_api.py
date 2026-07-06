"""次元拡張API(FR-SC)と監査エクスポート(FR-GV-03)の結合テスト。"""

from __future__ import annotations

import hashlib
import json

from aios_api.main import create_app
from fastapi.testclient import TestClient

DIM = 16  # store.DEMO_DIM


def _client() -> TestClient:
    return TestClient(create_app())


def _create(client: TestClient, name: str, k: int = 4) -> dict:
    return client.post("/v1/cohorts", json={"name": name, "slot_count": k}).json()


class TestScalingApi:
    def test_expand_and_axes(self) -> None:
        client = _client()
        cohort = _create(client, "scale-t1")
        cid = cohort["cohort_id"]

        res = client.post(
            f"/v1/cohorts/{cid}/scaling/expand",
            json={"added_dims": 4, "axis_labels": ["倫理的配慮", "法務", "創造性", "簡潔さ"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["previous_dimension"] == DIM
        assert body["new_dimension"] == DIM + 4
        assert body["slot_count"] == 4  # 請求項9: モデル数維持

        axes = client.get(f"/v1/cohorts/{cid}/scaling/axes").json()
        assert axes["dimension"] == DIM + 4
        assert [a["label"] for a in axes["axes"]] == ["倫理的配慮", "法務", "創造性", "簡潔さ"]

        # 拡張後も運用継続(無停止、NFR-SC-03)
        assert client.post(f"/v1/cohorts/{cid}/cycles/run").status_code == 200

    def test_label_count_mismatch_422(self) -> None:
        client = _client()
        cid = _create(client, "scale-t2")["cohort_id"]
        res = client.post(
            f"/v1/cohorts/{cid}/scaling/expand",
            json={"added_dims": 2, "axis_labels": ["only-one"]},
        )
        assert res.status_code == 422


class TestAuditExport:
    def test_ndjson_export_with_integrity(self) -> None:
        """NDJSON本文とマニフェストが整合し、行単位でチェーン検証情報を含む。"""
        client = _client()
        cohort = _create(client, "export-t1")
        cid = cohort["cohort_id"]
        client.post(f"/v1/cohorts/{cid}/cycles/run")
        client.post(f"/v1/cohorts/{cid}/tasks", json={"input": {}})

        res = client.get(f"/v1/lineage/export/{cid}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/x-ndjson")
        # 本文ハッシュがヘッダの提示値と一致(受領側の完全性検証)
        assert hashlib.sha256(res.content).hexdigest() == res.headers["X-AIOS-Export-SHA256"]

        lines = [json.loads(line) for line in res.text.strip().splitlines()]
        assert all(
            {"slot_id", "event_type", "generation", "prev_hash", "hash"} <= set(line)
            for line in lines
        )

        manifest = client.get(f"/v1/lineage/export/{cid}/manifest").json()
        assert manifest["total_events"] == len(lines)
        assert all(s["chain_verified"] for s in manifest["slots"])

        # マニフェストの末尾hashが本文の各スロット最終行と一致
        for s in manifest["slots"]:
            slot_lines = [line for line in lines if line["slot_id"] == s["slot_id"]]
            assert slot_lines[-1]["hash"] == s["last_hash"]

    def test_export_unknown_cohort_404(self) -> None:
        assert _client().get("/v1/lineage/export/nonexistent").status_code == 404
