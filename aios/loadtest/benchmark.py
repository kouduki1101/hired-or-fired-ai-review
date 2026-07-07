"""インプロセス性能ベンチマーク(NFR-PF 実測、docs/02)。

外部ネットワーク・DB を介さず、ASGI アプリを直接叩いて制御プレーンの
サーバサイド計算コスト(ルーティング・サイクル・参照)の分布を測る。
分散 HTTP 負荷試験は locustfile.py(デプロイ済み API 向け)を使う。

実行:
    uv run python loadtest/benchmark.py            # 既定: slots=20, N=2000
    uv run python loadtest/benchmark.py 50 5000    # slots=50, N=5000
"""

from __future__ import annotations

import statistics
import sys
import time
from collections.abc import Callable

from aios_api.main import create_app
from fastapi.testclient import TestClient


def _percentiles(samples_ms: list[float]) -> dict[str, float]:
    s = sorted(samples_ms)
    n = len(s)

    def pct(p: float) -> float:
        return s[min(n - 1, int(p * n))]

    return {
        "p50": pct(0.50),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": s[-1],
        "mean": statistics.fmean(s),
    }


def _bench(name: str, n: int, fn: Callable[[], object]) -> None:
    # ウォームアップ(JIT 的キャッシュ・初回割当を除外)
    for _ in range(min(20, n)):
        fn()
    latencies: list[float] = []
    start = time.perf_counter()
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        latencies.append((time.perf_counter() - t0) * 1000.0)
    wall = time.perf_counter() - start
    p = _percentiles(latencies)
    thr = n / wall
    print(
        f"{name:<28} n={n:<6} thr={thr:8.1f} req/s  "
        f"p50={p['p50']:6.2f}ms  p95={p['p95']:6.2f}ms  "
        f"p99={p['p99']:6.2f}ms  max={p['max']:6.2f}ms"
    )


def main() -> None:
    slot_count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 2000

    client = TestClient(create_app())  # devモード(認証なし=純計算コスト)
    cohort = client.post(
        "/v1/cohorts", json={"name": "bench", "slot_count": slot_count}
    ).json()
    cid = cohort["cohort_id"]

    task_body = {
        "input": {"messages": [{"role": "user", "content": "benchmark"}]},
        "metadata": {"importance": "normal", "difficulty": "normal"},
    }

    print(f"# AIOS control-plane benchmark  (slots={slot_count}, in-process ASGI)")
    print(f"# python={sys.version.split()[0]}\n")

    def post_task() -> object:
        return client.post(f"/v1/cohorts/{cid}/tasks", json=task_body)

    def get_metrics() -> object:
        return client.get(f"/v1/cohorts/{cid}/metrics/current")

    def get_cohort() -> object:
        return client.get(f"/v1/cohorts/{cid}")

    def run_cycle() -> object:
        return client.post(f"/v1/cohorts/{cid}/cycles/run")

    _bench("POST /tasks (routing)", n, post_task)
    _bench("GET  /metrics/current", n, get_metrics)
    _bench("GET  /cohorts/{id}", n, get_cohort)
    # サイクルは重いので回数を抑える
    _bench("POST /cycles/run", max(50, n // 20), run_cycle)


if __name__ == "__main__":
    main()
