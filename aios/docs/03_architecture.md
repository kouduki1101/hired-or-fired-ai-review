# 03. アーキテクチャ設計書

- 版数: 1.0 (Draft for Review)
- 前提: [00_product_overview.md](00_product_overview.md), [01_functional_requirements.md](01_functional_requirements.md)

---

## 1. アーキテクチャ概要

### 1.1 設計方針

1. **制御プレーン/データプレーン分離**: エージェント実体(データプレーン)はAdapter越しに操作し、AIOS本体は観測・判断・作用のみを持つ。推論経路(ルーティング)と制御ループ(指標→Rehatch)は独立に動き、制御停止時も推論は縮退継続する(NFR-AV-02)
2. **イベントソーシング**: スロットの状態・世代・制御判断はすべて追記専用イベントが正であり、読み取りモデル(スロット管理テーブル等)はイベントから導出される投影。リネージ(FR-GV)はイベント再生で成立する
3. **ヘキサゴナル(ポート&アダプタ)**: ドメインコア(指標演算・選定ポリシー)は純Pythonで外部依存ゼロ。LLM・埋め込み・ストレージ・通知はすべてポート経由
4. **特許5層モデルとの対応を保つ**: 明細書 図6の5層(卵層/固定母集団層/教師ベクトル層/散逸度・成長スコア層/オーケストレーション層)をコンポーネント境界として実装に写像する(§2)

### 1.2 コンポーネント構成(C4 Level 2)

```
┌─────────────────────────── AIOS Control Plane ────────────────────────────┐
│                                                                            │
│  [apps/dashboard]  Next.js ── SSE/REST ──┐                                 │
│                                          │                                 │
│  [apps/api]  FastAPI (REST / OpenAPI)    │                                 │
│   ├─ Task Gateway ──── Adaptive Router ──┼──────────────┐                  │
│   ├─ Admin/Config API                    │              │                  │
│   ├─ Governance API (lineage/audit)      │              │                  │
│   └─ Proposal API (agent→AIOS)           │              │                  │
│                                          │              │                  │
│  [apps/orchestrator]  制御ループ常駐プロセス  │              │                  │
│   └─ Phase FSM / Cycle Scheduler ────────┤              │                  │
│                                          ▼              ▼                  │
│  [packages/core]  ドメインコア(純関数)   ┌──────────────────────────┐        │
│   ├─ metrics: TV(EMA)/散逸度/適合度/成熟度│  Message Bus (Redis      │        │
│   ├─ policy: Rehatch選定/健全性判定/     │  Streams / NATS)         │        │
│   │          ダイナミクス調整/成熟点     └───────┬──────────────────┘        │
│   └─ lineage: イベント→系譜復元                  │                          │
│                                                 ▼                          │
│  [apps/worker]  非同期ワーカー群(水平スケール)                                 │
│   ├─ ProbeWorker(定点プローブ実行・埋め込み取得)                               │
│   ├─ MetricsWorker(指標演算・投影更新)                                       │
│   ├─ RehatchWorker(戦略実行・検証・ロールバック)                               │
│   └─ NotifyWorker(Webhook/Slack/メール)                                     │
│                                                                            │
│  Storage: PostgreSQL16+pgvector(状態/イベント/埋め込み)                       │
│           Object Storage(モデル構成スナップショット/アーカイブ)                 │
│           Redis(キャッシュ/ルーティング用最新指標/レート制御)                    │
└────────────┬───────────────────────────────────────────────┬───────────────┘
             │ Adapter SPI                                    │ Provider SPI
             ▼                                                ▼
   Data Plane: エージェント群                        LLM / Embedding Providers
   (LLM Agent / LoRA / Classical ML)               (Anthropic API 等)
```

## 2. 特許5層モデル → 実装マッピング

| 特許の層(図6) | 実装コンポーネント | 主な責務 |
|---|---|---|
| [5] オーケストレーション層 | `apps/orchestrator` + `core/policy` | 制御サイクル駆動、Rehatch可否判断、タスク割当方針、学習率/ノイズ調整の発行、提案の調停(FR-GV-04) |
| [4] 散逸度・成長スコア層 | `core/metrics` + MetricsWorker | 散逸度・適合度・成熟度・拡張指標の算出(純関数)と永続化 |
| [3] 教師ベクトル層 | `core/metrics.teacher` + `teacher_vectors` テーブル | EMAによるTV更新、次元管理(価値軸レジストリ)、NL教師ベクトル統合 |
| [2] 固定母集団層 | Cohort Store(`slots`/`slot_events`) | スロット・ID・世代・運用履歴の永続管理、No-Delete保証 |
| [1] 卵層 | Lifecycle Manager(Phase FSM内 `Hatchery` モジュール) | Phase1限定のK体生成。Phase2で呼出し不能に封印(コード上もフェーズガードで保証) |

## 3. 主要フロー設計

### 3.1 制御メインループ(明細書 図10/11、FR-LC-03)

```
CycleScheduler (周期 T=5min, テナント×コホート単位, 分散ロックで単一実行)
  1. Snapshot     : 稼働スロット一覧・現行TV・設定を読取り、cycle_id発行
  2. Probe        : ProbeWorkerへプローブ実行をファンアウト
                    → 各スロット出力の埋め込み E_i を収集(欠測は記録し除外)
  3. Compute      : core.metrics(純関数)で
                    C_t=centroid(E)  → TV_t=α·C_t+(1−α)·TV_{t−1}
                    D_t=dissipation(E) → 健全性判定(FIXED/STABLE/CHAOTIC)
                    F_i=fitness(E_i, TV_t)、成熟度更新
  4. Dynamics     : 健全性に応じ学習率補正・ノイズ量を決定(ヒステリシス付き)
                    → 制御信号イベント発行 → Adapter配布
  5. Select       : Rehatch対象選定(低適合/支配的/役割重複/停滞、lock・cooldown・上限適用)
  6. Actuate      : 承認モードなら承認キューへ、自動なら RehatchWorker へ指示
  7. Persist      : cycle結果(全指標・判断理由)をイベント+投影へ保存、通知発行
```

- 3〜5は純関数呼出しであり、同一入力での再現(監査時のリプレイ)が可能
- dry-runモードは6をスキップし、判断のみ記録する

### 3.2 タスクルーティング(明細書 図14/15、FR-RT)

```
POST /v1/cohorts/{id}/tasks
  → 分類(メタデータ or 軽量分類器): importance × difficulty × category
  → Redis上の最新指標キャッシュから ACTIVE スロットの (maturity, fitness) を取得
  → クラスタ判定: Veteran = maturity≥θ_m ∧ fitness≥θ_f / Rookie = それ以外
  → 割当: 高重要度→Veteran内で負荷分散 / 探索的→Rookie優先(経験付与)
       集中検出: 直近窓の割当シェア>30%のスロットは候補降格
  → Adapter.invoke() で推論実行 → 応答
  → routing_decision + task_result + maturity加算 をイベント記録(リネージ)
```

- 経路はDBを同期参照しない(Redisキャッシュ+非同期イベント書込)ことで p95<50ms を満たす
- 制御ループ停止時: キャッシュの最終値で継続(NFR-AV-02)

### 3.3 Rehatch実行(明細書 図12、FR-RH)

```
RehatchWorker:
  1. Lock       : slot状態 ACTIVE→REHATCHING(CAS)。rehatch_lock確認
  2. Source     : TV_t / 知識アーカイブをマッチング取得(保存時TVとの距離)
  3. Execute    : Adapterのcapabilitiesに応じ戦略実行
                  Prompt-Recompose | TV-Init | Adapter-Regen | Distillation
                  (混合率βで現構成とブレンド)
  4. Verify     : スモークプローブ(最小プローブセット)で健全性検証
                  失敗 → 直前世代スナップショットへロールバック → イベント記録
  5. Commit     : generation+1、構成スナップショット保存、成熟度リセット/減算
  6. Unlock     : REHATCHING→ACTIVE、rehatch_completed イベント、通知
```

### 3.4 安全境界監視(FR-SF)

- ProbeWorker/タスク応答の埋め込みを常時 `negative_centroids` と照合(pgvector近傍検索)
- 類似度>θ_danger でスロットを `QUARANTINED`(即時、制御サイクルを待たない)→ アラート → 復旧Rehatchフローへ
- 当該スロットの当サイクル寄与を除外しTV再計算(FR-SF-03)

### 3.5 次元拡張(明細書 図5、FR-SC)

```
POST /v1/cohorts/{id}/scaling/expand  {added_dims: M, axis_labels:[...]} (承認ゲート対象)
  1. TVをN+M次元へ拡張(旧履歴はゼロパディングで互換保持)
  2. 各Adapterへ次元整合指示(zero-pad / projection layer)
  3. 拡張次元の分散拡大誘導(ノイズ方向重み付け)を有効化
  4. dimension_expanded イベント記録(価値軸レジストリ更新)
```

## 4. コンポーネント詳細設計

### 4.1 apps/api(FastAPI)

| モジュール | 責務 |
|---|---|
| `routers/tasks` | タスク受付・ルーティング・結果返却(FR-RT) |
| `routers/cohorts` | コホート/スロットの参照・設定(削除エンドポイントなし) |
| `routers/rehatch` | 手動Rehatch指示・承認キュー操作(FR-RH-03, FR-GV-05) |
| `routers/lineage` | 開示請求応答・監査エクスポート(FR-GV-01〜03) |
| `routers/proposals` | エージェント自律提案の受付(FR-GV-04) |
| `routers/scaling` | 次元拡張(FR-SC) |
| `routers/safety` | 禁止ベクトル管理・隔離操作(FR-SF) |
| `routers/admin` | テナント・認証・プローブセット・閾値設定 |
| `middleware` | 認証(APIキー/OIDC)、RBAC、テナントコンテキスト、レート制限、監査記録 |

### 4.2 packages/core(ドメインコア: 外部依存なし・純関数)

```
core/
├── metrics/
│   ├── teacher.py        # EMA更新、NL教師ベクトル統合、次元拡張演算
│   ├── dissipation.py    # 散逸度①〜⑤の各アルゴリズム(Strategy)
│   ├── fitness.py        # コサイン適合度、報酬モデル適合度
│   ├── maturity.py       # 成熟度の加算/リセット/減算規則
│   └── extended.py       # 興味関数・認知方向・進化係数
├── policy/
│   ├── health.py         # 閾値+ヒステリシスによる FIXED/STABLE/CHAOTIC 判定
│   ├── rehatch_select.py # 対象選定(低適合/支配的/重複/停滞、上限・cooldown)
│   ├── dynamics.py       # 学習率/ノイズ調整量の決定
│   ├── routing.py        # クラスタ分類・割当スコアリング
│   ├── arbitration.py    # 自律提案の承認/否認判定
│   └── stabilization.py  # 成熟点(3指標収束)検出
├── lineage/
│   ├── events.py         # イベント型定義(Pydantic)・ハッシュチェーン
│   └── replay.py         # イベント再生による系譜/当時状態復元
└── types.py              # SlotState, CohortPhase, HealthStatus 等の値オブジェクト
```

### 4.3 Adapter SPI(packages/adapters)

```python
class ModelAdapter(Protocol):
    def capabilities(self) -> AdapterCapabilities: ...   # 対応Rehatch戦略・状態取得方式
    async def invoke(self, task: TaskInput, dynamics: DynamicsSignal) -> TaskOutput: ...
    async def get_state(self, probes: list[Probe]) -> SlotStateVector: ...  # 出力埋め込み or パラメータ
    async def apply_params(self, config: ModelConfig) -> ApplyResult: ...   # Rehatch適用(冪等)
    async def apply_dynamics(self, signal: DynamicsSignal) -> None: ...     # 温度/学習率/ノイズの解釈
```

- `ModelConfig` は広義の内部パラメータ: `system_prompt / context_vector / hyperparams(temperature等) / kb_access_policy / adapter_weights_ref`(¶0057)
- 同梱実装: `AnthropicAgentAdapter` / `OpenAICompatAdapter` / `LoraPeftAdapter`(S) / `SklearnAdapter`(C)
- 適合テストキット: `adapters/conformance/` — capabilities宣言と実挙動の一致、冪等性、ロールバック可否を検証

### 4.4 ストレージ選定

| データ | ストア | 理由 |
|---|---|---|
| スロット/コホート/設定(投影) | PostgreSQL | トランザクション整合、`ON DELETE RESTRICT` |
| イベントストア | PostgreSQL(追記専用テーブル、月次パーティション) | 監査整合性・ハッシュチェーン。将来量次第でKafka+アーカイブに拡張可能な抽象 |
| 埋め込み(プローブ出力/TV履歴/禁止ベクトル) | pgvector | 近傍検索(安全監視・アーカイブマッチング)を同一DBで完結 |
| モデル構成スナップショット/パラメータ | S3互換オブジェクトストレージ | 大容量・バージョニング・コールド階層 |
| 最新指標キャッシュ/レート制御/分散ロック | Redis | ルーティング低レイテンシ(NFR-PF-01) |
| ジョブ/イベント配送 | Redis Streams(GA) → NATS JetStream(スケール時) | 運用部品を最小化 |

### 4.5 マルチテナント

- 単一DB・行レベル分離(全テーブル `tenant_id`+RLSポリシー)+アプリ層二重チェック(NFR-SE-02)
- Enterprise: テナント専用スキーマ/DBオプション。暗号鍵はテナント別(KMS)
- ワーカーはテナント公平スケジューリング(1テナントの重いDistillationが他を飢餓させない)

## 5. デプロイ構成

### 5.1 SaaS(Kubernetes)

```
Ingress → api(HPA) / dashboard
        orchestrator(コホート分割シャーディング, leader election)
        worker: probe / metrics / rehatch / notify(それぞれHPA, キュー長でスケール)
        PostgreSQL(HA, pgvector) / Redis(HA) / Object Storage
        Observability: OTel Collector → Prometheus/Grafana/Loki
```

### 5.2 Self-Hosted

- 評価用: `docker compose up`(全部入り、単一ノード)
- 本番: Helm Chart(上記と同構成、外部DB/S3指定可)、エアギャップ用イメージバンドル

## 6. 障害モードと縮退設計(要点)

| 障害 | 挙動 |
|---|---|
| LLM/Embedding API障害 | プローブ欠測扱い(EMA更新スキップ)。ルーティングは継続。連続N回欠測でアラート |
| orchestrator停止 | 推論・ルーティングは最終指標で継続。復帰後、欠測サイクルは補完しない(欠測記録のみ) |
| Rehatch中クラッシュ | 起動時リカバリ: REHATCHING滞留スロットを検出し、スナップショットへロールバック |
| DB障害 | APIは503。イベントはローカルスプール(短期)後に再送 |
| Redis障害 | ルーティングはDB直読みへフォールバック(レイテンシ悪化を許容)、レート制限は保守側 |

## 7. 技術スタック(確定案)

| 層 | 技術 | 備考 |
|---|---|---|
| API/ワーカー/オーケストレータ | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, asyncio | 型必須(mypy strict) |
| ドメインコア | 純Python + NumPy | 外部I/Oなし |
| DB | PostgreSQL 16 + pgvector, Alembic | |
| キュー/キャッシュ | Redis 7(Streams) | スケール時NATS JetStream |
| ダッシュボード | Next.js 15, TypeScript, Tailwind, ECharts | SSE購読 |
| SDK | Python / TypeScript(OpenAPIから生成+手書き高水準API) | |
| LLM既定 | Anthropic API(claude-sonnet-5 既定、分類は claude-haiku-4-5) | Adapter抽象で差替可 |
| IaC/配布 | Docker, Helm, Terraform(SaaS), GitHub Actions | |
| 可観測性 | OpenTelemetry, Prometheus, Grafana, Loki | |
