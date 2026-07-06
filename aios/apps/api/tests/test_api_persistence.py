"""API永続化配線: 再起動(プロセス再作成)を跨いだrehydrate(NFR-AV-03)。"""

from __future__ import annotations

from pathlib import Path

from aios_api.main import create_app
from aios_api.store import STORE
from fastapi.testclient import TestClient


class TestRestartRehydrate:
    def test_cohort_survives_restart(self, tmp_path: Path) -> None:
        url = f"sqlite+aiosqlite:///{tmp_path}/aios.db"

        # --- 1回目の「プロセス」: 作成→運用→(persistは各操作後に自動) ---
        with TestClient(create_app(database_url=url)) as client:
            cohort = client.post(
                "/v1/cohorts", json={"name": "persistent-cohort", "slot_count": 4}
            ).json()
            cid = cohort["cohort_id"]
            for _ in range(2):
                assert client.post(f"/v1/cohorts/{cid}/cycles/run").status_code == 200
            client.post(f"/v1/cohorts/{cid}/tasks", json={"input": {}})
            before = client.get(f"/v1/cohorts/{cid}").json()

        # --- 再起動: インメモリ状態を破棄し、同じDBで新アプリを起動 ---
        STORE.clear_memory()
        with TestClient(create_app(database_url=url)) as client:
            listed = client.get("/v1/cohorts").json()
            assert cid in [c["cohort_id"] for c in listed]

            after = client.get(f"/v1/cohorts/{cid}").json()
            assert after["name"] == "persistent-cohort"
            assert after["phase"] == "OPERATING"
            # スロットのID・世代・成熟度が再起動を跨いで一致(請求項1)
            key = lambda s: s["display_id"]  # noqa: E731
            for b, a in zip(
                sorted(before["slots"], key=key), sorted(after["slots"], key=key), strict=True
            ):
                assert a["slot_id"] == b["slot_id"]
                assert a["generation"] == b["generation"]
                assert a["maturity"] == b["maturity"]

            # 復元後も運用を継続できる(step_noは保存値から+1)
            result = client.post(f"/v1/cohorts/{cid}/cycles/run").json()
            assert result["step_no"] == 3

            # 運用履歴もチェーン検証付きで引ける
            slot_id = after["slots"][0]["slot_id"]
            history = client.get(f"/v1/lineage/slots/{slot_id}/history").json()
            assert history["chain_verified"] is True
            assert history["events"][0]["event_type"] == "SLOT_CREATED"

    def test_no_database_url_is_memory_only(self) -> None:
        """DB未設定時は従来どおりインメモリで動作する(persistはno-op)。"""
        with TestClient(create_app()) as client:
            res = client.post("/v1/cohorts", json={"name": "mem-only", "slot_count": 2})
            assert res.status_code == 201
