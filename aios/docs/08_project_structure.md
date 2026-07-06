# 08. プロジェクトフォルダ構成

- 版数: 1.0 (Draft for Review)
- 形態: モノレポ(Python: uv workspace / TypeScript: pnpm workspace)。リポジトリ名: `aios`

---

## 1. 全体構成

```
aios/
├── README.md                        # 概要・クイックスタート
├── LICENSE / NOTICE                 # 商用ライセンス+特許表示(NFR-CP-05)
├── Makefile                         # dev/test/lint/build の統一入口
├── pyproject.toml                   # uv workspace ルート(Pythonツールチェーン統一設定)
├── pnpm-workspace.yaml              # TS workspace(dashboard, sdk-ts)
├── .github/
│   └── workflows/
│       ├── ci.yml                   # lint→typecheck→unit→integration→build
│       ├── security.yml             # SCA・コンテナスキャン(NFR-SE-06)
│       └── release.yml              # イメージ/Helm/SDK公開
│
├── apps/                            # 実行可能アプリケーション(デプロイ単位)
│   ├── api/                         # FastAPI コントロールプレーンAPI
│   │   ├── src/aios_api/
│   │   │   ├── main.py              # アプリ組立て(DI・ミドルウェア)
│   │   │   ├── routers/             # tasks/cohorts/rehatch/lineage/proposals/
│   │   │   │                        # scaling/safety/approvals/admin(05_api準拠)
│   │   │   ├── middleware/          # auth(APIキー/OIDC), rbac, tenant_context,
│   │   │   │                        # rate_limit, audit
│   │   │   ├── schemas/             # リクエスト/レスポンスDTO(OpenAPI一次定義)
│   │   │   └── deps.py              # 依存注入(ストア・バス・設定)
│   │   ├── tests/
│   │   │   ├── contract/            # ★スキーマテスト: slot DELETE不存在、
│   │   │   │                        #   Phase2でのslot追加409 等の請求項保証
│   │   │   └── ...
│   │   └── Dockerfile
│   │
│   ├── orchestrator/                # 制御ループ常駐プロセス(図10のメインループ)
│   │   ├── src/aios_orchestrator/
│   │   │   ├── scheduler.py         # CycleScheduler(分散ロック・コホートシャーディング)
│   │   │   ├── cycle.py             # 1サイクルの実行(Snapshot→Probe→Compute→
│   │   │   │                        #   Dynamics→Select→Actuate→Persist)
│   │   │   ├── phase_fsm.py         # INITIALIZING→CALIBRATING→OPERATING(請求項10)
│   │   │   ├── hatchery.py          # 卵層: Phase1限定のK体生成。フェーズガード付き
│   │   │   └── recovery.py          # 起動時リカバリ(REHATCHING滞留の解消)
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   ├── worker/                      # 非同期ワーカー群(キュー消費、水平スケール)
│   │   ├── src/aios_worker/
│   │   │   ├── probe_worker.py      # 定点プローブ実行・埋め込み取得
│   │   │   ├── metrics_worker.py    # 指標演算・投影更新(coreを呼ぶだけ)
│   │   │   ├── rehatch_worker.py    # 戦略実行・スモーク検証・ロールバック
│   │   │   ├── safety_worker.py     # 禁止ベクトル照合・隔離(即時系)
│   │   │   └── notify_worker.py     # Webhook/Slack/メール配送(署名・リトライ)
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   └── dashboard/                   # Next.js 群健全性ダッシュボード(図16)
│       ├── src/
│       │   ├── app/                 # (App Router)
│       │   │   ├── cohorts/[id]/    # メイン画面
│       │   │   ├── approvals/       # 承認キュー
│       │   │   └── audit/           # 監査ログ・リネージ検索
│       │   ├── components/
│       │   │   ├── StatusHeader.tsx      # FR-UI-01
│       │   │   ├── DissipationMeter.tsx  # FR-UI-02(FIXED/STABLE/CHAOTIC 3ゾーン)
│       │   │   ├── TrendChart.tsx        # FR-UI-03(TV太線+スロット軌跡細線)
│       │   │   ├── DynamicsMonitor.tsx   # FR-UI-04
│       │   │   ├── SlotTiles.tsx         # FR-UI-05(雛アイコン含む)
│       │   │   └── EventLog.tsx          # FR-UI-06
│       │   └── lib/                 # APIクライアント(sdk-ts利用)、SSE購読
│       ├── tests/
│       └── Dockerfile
│
├── packages/                        # 再利用ライブラリ(デプロイされない)
│   ├── core/                        # ★ドメインコア: 外部I/Oゼロの純関数(NFR-MT-02)
│   │   ├── src/aios_core/
│   │   │   ├── metrics/             # teacher.py / dissipation.py / fitness.py /
│   │   │   │                        # maturity.py / extended.py(06_algorithm準拠)
│   │   │   ├── policy/              # health.py / rehatch_select.py / dynamics.py /
│   │   │   │                        # routing.py / arbitration.py / stabilization.py
│   │   │   ├── lineage/             # events.py(型+ハッシュチェーン) / replay.py
│   │   │   └── types.py
│   │   └── tests/                   # property-based test含む(hypothesis)
│   │
│   ├── adapters/                    # Model Adapter SPI と同梱実装
│   │   ├── src/aios_adapters/
│   │   │   ├── spi.py               # ModelAdapter Protocol / ModelConfig /
│   │   │   │                        # DynamicsSignal / AdapterCapabilities
│   │   │   ├── anthropic_agent.py   # LLM APIエージェント(GA既定)
│   │   │   ├── openai_compat.py
│   │   │   ├── lora_peft.py         # (S) 自前ホストLoRA+HyperNet
│   │   │   ├── sklearn_generic.py   # (C)
│   │   │   └── embeddings/          # Embedding Provider抽象+実装
│   │   ├── conformance/             # ★Adapter適合テストキット(NFR-MT-04)
│   │   └── tests/
│   │
│   ├── storage/                     # 永続化実装(ポートの実装側)
│   │   ├── src/aios_storage/
│   │   │   ├── models.py            # SQLAlchemyモデル(04_data_model準拠)
│   │   │   ├── repositories/        # cohort/slot/event/tv/archive/task リポジトリ
│   │   │   ├── event_store.py       # 追記+ハッシュチェーン挿入検証
│   │   │   ├── projections.py       # イベント→slots投影の更新/再構築
│   │   │   ├── object_store.py      # S3互換(スナップショット・原文TTL)
│   │   │   └── cache.py             # Redis(最新指標・分散ロック・レート)
│   │   └── migrations/              # Alembic
│   │
│   ├── common/                      # 横断: 設定(pydantic-settings)、OTel計装、
│   │                                # 構造化ログ、エラー型、冪等キー、暗号/KMS
│   ├── sdk-python/                  # 公開SDK(OpenAPI生成+高水準層)
│   └── sdk-ts/                      # 公開SDK(TypeScript)
│
├── infra/
│   ├── docker-compose.yml           # 評価用全部入り(postgres+pgvector, redis, minio, 全apps)
│   ├── helm/aios/                   # 本番チャート(values: SaaS/self-hosted プロファイル)
│   ├── terraform/                   # SaaS環境(セル単位)
│   └── grafana/                     # ダッシュボード定義・アラートルール(NFR-OP-01)
│
├── tests/
│   ├── integration/                 # DB/Redis込みの結合(testcontainers)
│   ├── e2e/                         # docker-compose起動→シナリオ:
│   │   ├── test_lifecycle.py        #   卵層→運用→固着注入→自動復旧
│   │   ├── test_rehatch_lineage.py  #   Rehatch→開示請求で世代系譜が引ける
│   │   ├── test_claims.py           # ★請求項1〜10の実施を通しで検証する回帰スイート
│   │   └── test_safety.py           #   禁止ベクトル→隔離→復旧
│   └── load/                        # k6: ルーティングp95<50ms、イベント1000/s(NFR-PF)
│
├── docs/                            # 本仕様書群(00〜08)+ ADR
│   └── adr/                         # Architecture Decision Records
└── examples/
    ├── quickstart-support-agents/   # サポートエージェント20体の導入例
    └── custom-adapter/              # サードパーティAdapter実装例
```

## 2. 依存方向の規約(強制: import-linter)

```
apps/*  →  packages/{core, adapters, storage, common}
storage →  common(coreへ依存しない: リポジトリはDTO変換で分離)
adapters → common, core(types のみ)
core    →  (依存なし: NumPyのみ)
sdk-*   →  (本体へ依存しない: OpenAPI契約のみ共有)
```

- `core` にI/O(HTTP/DB/ファイル)を持ち込むPRはCIで機械的に落とす
- 請求項保証テスト(`tests/e2e/test_claims.py`、`apps/api/tests/contract/`)はCI必須ゲート。
  「スロット削除APIが存在しない」「Phase2でスロット追加不可」「Rehatch後もslot_id/履歴連続」を常時回帰

## 3. ブランチ・リリース運用

| 項目 | 規約 |
|---|---|
| ブランチ | trunk-based(`main`)+短命feature branch。`release/x.y` で安定化 |
| バージョニング | SemVer。公開API破壊はメジャーのみ(NFR-MT-03) |
| 成果物 | コンテナイメージ(api/orchestrator/worker/dashboard)、Helm Chart、SDK(PyPI/npm)、オフラインバンドル |
| DBマイグレーション | 後方互換2バージョン(expand→migrate→contract) |
