# AIOS 負荷試験 / 性能計測

制御プレーン(`apps/api`)の性能を2つの粒度で測る。目標値は
[`../docs/02_nonfunctional_requirements.md`](../docs/02_nonfunctional_requirements.md)
の NFR-PF / NFR-SC。

## 1. インプロセス・ベンチマーク — `benchmark.py`

外部ネットワーク・DB を介さず ASGI アプリを直接叩き、**サーバサイド計算コスト**
(タスクルーティング判断・制御サイクル・参照)のレイテンシ分布を測る。
CI・ローカルで再現性高く回せる。推論そのものの時間は含まない(NFR-PF-01/02 の対象)。

```bash
uv run python loadtest/benchmark.py            # 既定: slots=20, N=2000
uv run python loadtest/benchmark.py 50 5000    # slots=50, N=5000
```

出力は各エンドポイントの `thr(req/s) / p50 / p95 / p99 / max`。
最新の実測値は docs/02「性能実測ベースライン」に転記済み。

> 注: 出力の `thr` は単一スレッド同期クライアントの直列値。実効スループットは下記 Locust で測る。

## 2. 分散 HTTP 負荷試験 — `locustfile.py`

デプロイ済み(または `make dev` で起動した)API に実ネットワーク越しで同時多重負荷をかけ、
実効スループット・テール遅延・エラー率を測る。読み書き混在(route:read:cycle = 20:8:2)。

```bash
pip install locust    # 依存に含めていない(計測時のみ)
locust -f loadtest/locustfile.py --host http://localhost:8080 \
       --users 200 --spawn-rate 20 --run-time 5m --headless
```

認証を有効化した環境では:

```bash
export AIOS_LOADTEST_API_KEY=key1        # X-API-Key を付与
# もしくは
export AIOS_LOADTEST_BEARER=<jwt>        # Authorization: Bearer を付与
```

### レプリカ構成に関する注意

コホート状態はプロセス内保持(Helm `values.yaml` の `api.replicas=1` 推奨)。
複数レプリカで負荷試験する場合はスティッキーセッション、または単一レプリカで実施する。
永続化(`AIOS_DATABASE_URL`)有効時は再起動をまたいで rehydrate されるが、
実行時のコホート操作は担当レプリカに集約される前提。
