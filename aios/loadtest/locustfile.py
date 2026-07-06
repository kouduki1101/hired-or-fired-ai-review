"""分散 HTTP 負荷試験(NFR-PF / NFR-SC、デプロイ済み API 向け)。

ベンチマーク(benchmark.py)がサーバサイド計算コストをインプロセスで測るのに対し、
こちらは実ネットワーク越しに同時多重負荷をかけ、レプリカ構成での実効スループット・
テール遅延・エラー率を測る。

実行例:
    # API を起動しておく(例: make dev / helm でデプロイ済み URL)
    locust -f loadtest/locustfile.py --host http://localhost:8080 \
           --users 200 --spawn-rate 20 --run-time 5m --headless

認証:
    AIOS_LOADTEST_API_KEY を設定すると X-API-Key を付与する。
    AIOS_LOADTEST_BEARER を設定すると Authorization: Bearer を付与する。

注意: コホートはプロセス内保持のため(NFR-AV 参照 / Helm values の api.replicas=1
推奨)、複数レプリカ構成ではスティッキーセッションか単一レプリカで実施すること。
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task


def _auth_headers() -> dict[str, str]:
    if key := os.environ.get("AIOS_LOADTEST_API_KEY"):
        return {"X-API-Key": key}
    if bearer := os.environ.get("AIOS_LOADTEST_BEARER"):
        return {"Authorization": f"Bearer {bearer}"}
    return {}


class OperatorUser(HttpUser):
    """1 コホートを作り、読み書き混在のワークロードを流す運用者ロール。"""

    wait_time = between(0.05, 0.3)

    def on_start(self) -> None:
        self.headers = _auth_headers()
        res = self.client.post(
            "/v1/cohorts",
            json={"name": f"load-{random.randint(0, 1_000_000)}", "slot_count": 20},
            headers=self.headers,
        )
        self.cohort_id = res.json()["cohort_id"] if res.status_code == 201 else None

    @task(20)
    def route_task(self) -> None:
        if not self.cohort_id:
            return
        self.client.post(
            f"/v1/cohorts/{self.cohort_id}/tasks",
            json={
                "input": {"messages": [{"role": "user", "content": "load"}]},
                "metadata": {"importance": random.choice(["low", "normal", "high"])},
            },
            headers=self.headers,
            name="/v1/cohorts/[id]/tasks",
        )

    @task(8)
    def read_metrics(self) -> None:
        if not self.cohort_id:
            return
        self.client.get(
            f"/v1/cohorts/{self.cohort_id}/metrics/current",
            headers=self.headers,
            name="/v1/cohorts/[id]/metrics/current",
        )

    @task(2)
    def run_cycle(self) -> None:
        if not self.cohort_id:
            return
        self.client.post(
            f"/v1/cohorts/{self.cohort_id}/cycles/run",
            headers=self.headers,
            name="/v1/cohorts/[id]/cycles/run",
        )
