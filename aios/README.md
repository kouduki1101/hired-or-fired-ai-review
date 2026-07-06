# AIOS — マルチエージェント群 長期運用基盤(群AIオペレーティングシステム)

特許第7745「システム、方法、プログラム」(特願2026-000860、令和8年4月特許査定・請求項12)に基づく、
複数の学習モデル/AIエージェントからなる「群」の運用プロセスを長期・安定・追跡可能に制御する
商用プロダクトの仕様・設計・実装計画一式。

## ドキュメント構成

| # | ドキュメント | 内容 |
|---|---|---|
| 00 | [製品概要](docs/00_product_overview.md) | 製品定義、ターゲット、提供形態、特許請求項トレーサビリティマトリクス |
| 01 | [機能要件](docs/01_functional_requirements.md) | FR-xxx 形式の機能要件定義(MoSCoW優先度付き) |
| 02 | [非機能要件](docs/02_nonfunctional_requirements.md) | 性能・可用性・セキュリティ・運用・コンプライアンス要件 |
| 03 | [アーキテクチャ設計](docs/03_architecture.md) | 全体構成、コンポーネント設計、制御ループ、5層モデルの実装対応 |
| 04 | [データモデル](docs/04_data_model.md) | ER図、テーブル定義(DDL)、イベントストア設計 |
| 05 | [API仕様](docs/05_api_specification.md) | REST API、Webhook、SDKインタフェース |
| 06 | [アルゴリズム設計](docs/06_algorithm_design.md) | 教師ベクトル/散逸度/適合度/Rehatch/ルーティング/次元拡張の数式と擬似コード |
| 07 | [実装計画](docs/07_implementation_plan.md) | フェーズ分割、マイルストーン、実装手順、Definition of Done |
| 08 | [プロジェクト構成](docs/08_project_structure.md) | モノレポのフォルダ構成と各モジュールの責務 |

## 実装状況(P4前半まで完了 — 請求項1〜10すべて実装・テスト済み)

| フェーズ | 状態 | 内容 |
|---|---|---|
| P0 基盤 | ✅ | uvモノレポ、CI、docker-compose(pgvector/redis/minio/api/dashboard) |
| P1 コア制御ループ | ✅ | 指標演算(EMA/散逸度/適合度)、Rehatch-in-Place、卵層非再入、e2e(固着→自動復旧) |
| P2 運用機能 | ✅ | スケジューラ、ルーティングAPI、リネージ/開示請求、自律提案調停、安全境界(禁止ベクトル→隔離→復旧)、ダッシュボード(図16)、永続化rehydrate、Webhook通知(HMAC署名) |
| P3 ガバナンス | ✅ | 次元拡張API(請求項9)、監査エクスポート(NDJSON+完全性マニフェスト)、承認ワークフロー(manual時のRehatch/拡張は承認キュー経由) |
| P4 商用化 | 前半✅ | 使用量メータリング、APIキー認証+テナント分離(コホート/承認/使用量/Webhookを分離、越境は404)。残: Alembic、OIDC/RBAC、Helm本番化、負荷試験、SDK公開 |

テスト: Python 172件 + API契約テスト(請求項保証)。ダッシュボードは実サーバ+Playwrightで描画検証済み。
請求項別の実装対応表は [docs/00_product_overview.md](docs/00_product_overview.md) §5 を参照。

## クイックスタート(ローカル)

```bash
cd aios
make install          # uv sync
make test             # 144 tests
make dev              # APIを :8080 で起動(インメモリ)
AIOS_DATABASE_URL=sqlite+aiosqlite:///./aios.db make dev   # 永続化有効(再起動でrehydrate)

cd apps/dashboard && npm install && npm run dev   # ダッシュボード :3000
```

APIだけで一巡する例:
```bash
curl -X POST :8080/v1/cohorts -H 'Content-Type: application/json' \
  -d '{"name":"demo","slot_count":10}'                     # 卵層→固定母集団の生成
curl -X POST :8080/v1/cohorts/<id>/cycles/run              # 制御サイクル(図10)1周
curl -X POST :8080/v1/cohorts/<id>/tasks -d '{"input":{}}' # 成熟度×適合度ルーティング
curl :8080/v1/lineage/tasks/<task_id>                      # 開示請求応答(誰が・なぜ)
```

## 読む順番

- **事業判断者**: 00 → 01 → 07
- **アーキテクト**: 00 → 03 → 04 → 05 → 06
- **実装者**: 03 → 06 → 08 → 07(担当フェーズ)

## 用語(本ドキュメント群共通)

| 用語 | 意味 | 特許上の対応 |
|---|---|---|
| スロット (Slot) | 削除が許容されない固定管理単位。エージェントの「席」 | 請求項2 |
| 教師ベクトル (Teacher Vector, TV) | 群の長期的な学習方向性を示す指標。EMAで更新 | 第1の指標(請求項1,3) |
| 散逸度 (Dissipation) | 群全体のばらつき度合い | 第2の指標(請求項1,4) |
| 適合度 (Fitness) | 各モデルの教師ベクトルへの整合度スコア | 請求項5 |
| 成熟度 (Maturity) | 最終Rehatchからの経過ステップ数/学習量 | 請求項8 |
| Rehatch | ID・運用履歴を維持したままの非破壊的再初期化 | 請求項1,5,6,10 |
| ダイナミクス調整 | 学習率/ノイズ量の動的制御 | 請求項7 |
| 次元拡張スケーリング | スロット数を増やさず教師ベクトルの次元を拡張 | 請求項9 |
| 卵層 (Egg Layer) | 初期化フェーズ専用のモデル生成層。定常運用後は非再入 | 請求項10 |
