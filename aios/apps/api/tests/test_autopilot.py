"""Autopilot(常駐駆動、FR-LC-03)の結合テスト。

TestClient を context manager で開くと lifespan が動き、ポータルのイベントループ上で
常駐タスクが実際に周期実行される。終了時は stop_all のグレースフル停止を通る。
"""

from __future__ import annotations

import time

from aios_api.main import create_app
from aios_api.store import STORE
from fastapi.testclient import TestClient


def _step_no(client: TestClient, cid: str) -> int:
    return client.get(f"/v1/cohorts/{cid}/metrics/current").json()["step_no"]


def _wait_until(cond, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


class TestAutopilot:
    def test_on_runs_cycles_and_off_stops(self) -> None:
        STORE.clear_memory()
        with TestClient(create_app()) as client:
            cohort = client.post("/v1/cohorts", json={"name": "ap", "slot_count": 3}).json()
            cid = cohort["cohort_id"]

            res = client.post(
                f"/v1/cohorts/{cid}/loop",
                json={"action": "autopilot_on", "interval_seconds": 0.05},
            )
            body = res.json()
            assert body["autopilot"] is True
            assert body["autopilot_interval_seconds"] == 0.05

            # 常駐がサイクルを自動で進める
            assert _wait_until(lambda: _step_no(client, cid) >= 2)

            # 停止 → 進行が止まる
            off = client.post(f"/v1/cohorts/{cid}/loop", json={"action": "autopilot_off"})
            assert off.json()["autopilot"] is False
            time.sleep(0.2)  # 実行中サイクルの排出
            frozen = _step_no(client, cid)
            time.sleep(0.3)
            assert _step_no(client, cid) == frozen

    def test_pause_skips_cycles_without_stopping_autopilot(self) -> None:
        STORE.clear_memory()
        with TestClient(create_app()) as client:
            cohort = client.post("/v1/cohorts", json={"name": "ap2", "slot_count": 3}).json()
            cid = cohort["cohort_id"]
            client.post(
                f"/v1/cohorts/{cid}/loop",
                json={"action": "autopilot_on", "interval_seconds": 0.05},
            )
            assert _wait_until(lambda: _step_no(client, cid) >= 1)

            # pause: autopilot は生きたままサイクルだけスキップ
            res = client.post(f"/v1/cohorts/{cid}/loop", json={"action": "pause"})
            assert res.json()["autopilot"] is True
            time.sleep(0.2)  # 実行中サイクルの排出
            frozen = _step_no(client, cid)
            time.sleep(0.3)
            assert _step_no(client, cid) == frozen

            # resume で再び進む
            client.post(f"/v1/cohorts/{cid}/loop", json={"action": "resume"})
            assert _wait_until(lambda: _step_no(client, cid) > frozen)

    def test_env_enables_autopilot_for_new_cohorts(
        self, monkeypatch,
    ) -> None:
        STORE.clear_memory()
        monkeypatch.setenv("AIOS_AUTOPILOT_INTERVAL_SECONDS", "0.05")
        with TestClient(create_app()) as client:
            cohort = client.post("/v1/cohorts", json={"name": "ap3", "slot_count": 3}).json()
            cid = cohort["cohort_id"]
            # 作成しただけで自動運転が始まっている
            assert _wait_until(lambda: _step_no(client, cid) >= 1)

    def test_manual_run_still_works_alongside(self) -> None:
        """手動 /cycles/run は常駐と同じサービス経路(挙動一致)を通る回帰確認。"""
        STORE.clear_memory()
        with TestClient(create_app()) as client:
            cohort = client.post("/v1/cohorts", json={"name": "ap4", "slot_count": 3}).json()
            cid = cohort["cohort_id"]
            summary = client.post(f"/v1/cohorts/{cid}/cycles/run").json()
            assert summary["step_no"] == 1
            # 使用量も従来どおり計上される
            usage = client.get("/v1/admin/usage").json()
            row = next(u for u in usage["cohorts"] if u["cohort_id"] == cid)
            assert row["cycles_run"] == 1
