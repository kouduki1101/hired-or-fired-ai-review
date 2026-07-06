# 04. データモデル設計書

- 版数: 1.0 (Draft for Review)
- DB: PostgreSQL 16 + pgvector。全テーブルに `tenant_id` を持ちRLS適用(記載省略)。`created_at/updated_at` は省略表記

---

## 1. ER 概観

```
tenants ─┬─ cohorts ─┬─ slots ──────────┬─ slot_events (追記専用)
         │           │                  ├─ model_snapshots
         │           │                  └─ task_records ─ routing_decisions
         │           ├─ teacher_vectors (時系列)
         │           ├─ cohort_cycles (制御サイクル履歴)
         │           ├─ probe_sets ─ probes
         │           ├─ probe_results (埋め込み)
         │           ├─ knowledge_archives
         │           ├─ negative_centroids
         │           ├─ value_axes (次元レジストリ)
         │           ├─ proposals (自律提案)
         │           └─ approval_requests
         ├─ users / api_keys / roles
         └─ audit_log (管理操作)
```

イベントソーシング方針: `slot_events` と `cohort_cycles` が一次事実。`slots` の指標カラムは投影(最新値キャッシュ)であり、イベント再生で再構築可能。

## 2. DDL(主要テーブル)

### 2.1 コホートとフェーズ

```sql
CREATE TYPE cohort_phase AS ENUM ('INITIALIZING', 'CALIBRATING', 'OPERATING'); -- 卵層→定常(請求項10)
CREATE TYPE health_status AS ENUM ('FIXED', 'STABLE', 'CHAOTIC', 'UNKNOWN');

CREATE TABLE cohorts (
  cohort_id       UUID PRIMARY KEY,
  tenant_id       UUID NOT NULL REFERENCES tenants,
  name            TEXT NOT NULL,
  phase           cohort_phase NOT NULL DEFAULT 'INITIALIZING',
  slot_count      INT  NOT NULL CHECK (slot_count BETWEEN 2 AND 1000), -- K: Phase1でのみ設定
  tv_dimension    INT  NOT NULL DEFAULT 1536,           -- 現在の教師ベクトル次元N
  cycle_interval  INTERVAL NOT NULL DEFAULT '5 minutes',
  ema_alpha       REAL NOT NULL DEFAULT 0.1 CHECK (ema_alpha > 0 AND ema_alpha <= 1),
  config          JSONB NOT NULL DEFAULT '{}',          -- 閾値・ポリシー・承認モード等(バージョン管理はconfig_revisionsで)
  loop_state      TEXT NOT NULL DEFAULT 'RUNNING'       -- RUNNING/PAUSED/DRY_RUN
);
```

### 2.2 スロット(固定母集団層) — 明細書 図7

```sql
CREATE TYPE slot_status AS ENUM ('ACTIVE','TRAINING','REHATCHING','QUARANTINED','DORMANT');

CREATE TABLE slots (
  slot_id          UUID PRIMARY KEY,
  cohort_id        UUID NOT NULL REFERENCES cohorts ON DELETE RESTRICT,  -- No-Delete
  display_id       TEXT NOT NULL,                      -- '001' 等。cohort内一意・不変
  generation       INT  NOT NULL DEFAULT 0,            -- Rehatchでインクリメント
  current_model_id UUID,                               -- → model_snapshots.snapshot_id
  adapter_kind     TEXT NOT NULL,                      -- 'anthropic_agent' | 'lora_peft' | ...
  status           slot_status NOT NULL DEFAULT 'ACTIVE',
  rehatch_lock     BOOLEAN NOT NULL DEFAULT FALSE,     -- 削除保護フラグ
  role_label       TEXT,
  -- 投影(最新値キャッシュ。正はイベント):
  maturity         BIGINT NOT NULL DEFAULT 0,          -- 学習ステップ/処理タスク数
  fitness          REAL,                               -- 最新適合度 [-1,1]→正規化[0,1]
  last_rehatch_at  TIMESTAMPTZ,
  UNIQUE (cohort_id, display_id)
);
-- スロット行のDELETEはDBロールでも禁止(REVOKE DELETE)。休止はstatus=DORMANT
```

### 2.3 運用履歴イベントストア(追記専用・ハッシュチェーン)

```sql
CREATE TYPE slot_event_type AS ENUM (
  'SLOT_CREATED','TASK_ASSIGNED','TASK_COMPLETED','TRAINING_STEP',
  'REHATCH_SELECTED','REHATCH_STARTED','REHATCH_COMPLETED','REHATCH_ROLLED_BACK',
  'STATUS_CHANGED','DYNAMICS_APPLIED','QUARANTINED','RESTORED',
  'PROPOSAL_SUBMITTED','PROPOSAL_DECIDED','CONFIG_CHANGED'
);

CREATE TABLE slot_events (
  event_id     BIGINT GENERATED ALWAYS AS IDENTITY,
  tenant_id    UUID NOT NULL,
  slot_id      UUID NOT NULL REFERENCES slots ON DELETE RESTRICT,
  cohort_id    UUID NOT NULL,
  cycle_id     UUID,                                   -- 発生元制御サイクル(任意)
  event_type   slot_event_type NOT NULL,
  generation   INT NOT NULL,                           -- 発生時点の世代
  payload      JSONB NOT NULL,                         -- 型はcore/lineage/events.pyで規定
  prev_hash    BYTEA NOT NULL,                         -- 同一slotの直前イベントhash
  hash         BYTEA NOT NULL,                         -- SHA-256(prev_hash || 正規化payload)
  occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);                    -- 月次パーティション
-- INSERTのみ許可(REVOKE UPDATE/DELETE)。月次で外部アンカー(hash先頭をaudit_logへ)
```

### 2.4 教師ベクトル(第1の指標)と価値軸 — 明細書 図8

```sql
CREATE TABLE teacher_vectors (
  tv_id        UUID PRIMARY KEY,
  cohort_id    UUID NOT NULL REFERENCES cohorts,
  cycle_id     UUID,                        -- 生成元サイクル(T_0はNULL)
  dimension    INT  NOT NULL,
  vector       vector NOT NULL,             -- pgvector(拡張時は新次元で保存、旧との比較はzero-pad)
  nl_directive TEXT,                        -- NL教師ベクトル(行動規範テキスト, FR-MT-05)
  source       TEXT NOT NULL,               -- 'ema_update' | 'initial' | 'dimension_expansion' | 'contamination_recalc'
  measured_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE value_axes (                    -- 次元レジストリ(FR-SC-01)
  cohort_id   UUID NOT NULL REFERENCES cohorts,
  dim_index   INT  NOT NULL,                -- 0-based
  label       TEXT NOT NULL,                -- '正確性','倫理的配慮',...
  added_at    TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (cohort_id, dim_index)
);
```

### 2.5 制御サイクル(指標管理データ) — 明細書 図8

```sql
CREATE TABLE cohort_cycles (
  cycle_id        UUID PRIMARY KEY,
  cohort_id       UUID NOT NULL REFERENCES cohorts,
  step_no         BIGINT NOT NULL,               -- 論理ステップ数(単調増加)
  tv_id           UUID REFERENCES teacher_vectors,
  dissipation     REAL,                          -- 第2の指標値
  dissipation_algo TEXT NOT NULL,                -- 'output_embedding' 等①〜⑤
  health          health_status NOT NULL,
  lr_correction   REAL NOT NULL DEFAULT 1.0,     -- 学習率補正値
  noise_amount    REAL NOT NULL DEFAULT 0.0,     -- ノイズ付加量
  fitness_mean    REAL, fitness_min REAL, fitness_max REAL,
  rehatch_count   INT NOT NULL DEFAULT 0,
  probe_missing   INT NOT NULL DEFAULT 0,        -- 欠測スロット数
  dry_run         BOOLEAN NOT NULL DEFAULT FALSE,
  decisions       JSONB NOT NULL,                -- 選定理由・調停結果の構造化記録
  measured_at     TIMESTAMPTZ NOT NULL,
  UNIQUE (cohort_id, step_no)
);
```

### 2.6 プローブと埋め込み

```sql
CREATE TABLE probe_sets (
  probe_set_id UUID PRIMARY KEY,
  cohort_id    UUID NOT NULL REFERENCES cohorts,
  version      INT NOT NULL,
  purpose      TEXT NOT NULL DEFAULT 'metrics',   -- 'metrics' | 'smoke'(Rehatch検証用)
  is_active    BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (cohort_id, version, purpose)
);
CREATE TABLE probes (
  probe_id     UUID PRIMARY KEY,
  probe_set_id UUID NOT NULL REFERENCES probe_sets,
  input        JSONB NOT NULL,                    -- プロンプト/特徴量
  weight       REAL NOT NULL DEFAULT 1.0
);
CREATE TABLE probe_results (
  result_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cycle_id     UUID NOT NULL,
  slot_id      UUID NOT NULL,
  generation   INT NOT NULL,
  probe_id     UUID NOT NULL,
  embedding    vector NOT NULL,                   -- 出力埋め込み
  raw_output_ref TEXT,                            -- 原文はオブジェクトストレージ(TTL, NFR-CP-03)
  measured_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX ON probe_results USING ivfflat (embedding vector_cosine_ops); -- 安全監視・類似検索
```

### 2.7 モデル構成スナップショットと知識アーカイブ — 明細書 図9

```sql
CREATE TABLE model_snapshots (
  snapshot_id   UUID PRIMARY KEY,
  slot_id       UUID NOT NULL REFERENCES slots,
  generation    INT NOT NULL,
  adapter_kind  TEXT NOT NULL,
  config        JSONB NOT NULL,        -- system_prompt/context_vector参照/hyperparams/kb_access_policy
  params_uri    TEXT,                  -- 重み実体(オブジェクトストレージ)。LLM APIエージェントはNULL可
  created_by    TEXT NOT NULL,         -- 'hatchery' | 'rehatch:<strategy>' | 'rollback'
  UNIQUE (slot_id, generation)
);

CREATE TABLE knowledge_archives (       -- 知識継承用データ(図9)
  archive_id     UUID PRIMARY KEY,
  cohort_id      UUID NOT NULL REFERENCES cohorts,
  kind           TEXT NOT NULL,        -- 'elite_model' | 'trend_mean' | 'stabilization_snapshot'
  source_slot_id UUID, source_generation INT,
  tv_id          UUID REFERENCES teacher_vectors,  -- 関連トレンド情報(保存時TV)
  params_uri     TEXT,                 -- 凍結パラメータ/構成
  best_score     REAL,                 -- 獲得時最高スコア
  distill_allowed BOOLEAN NOT NULL DEFAULT TRUE,   -- 蒸留使用許可フラグ
  archived_at    TIMESTAMPTZ NOT NULL,
  storage_tier   TEXT NOT NULL DEFAULT 'hot'       -- 'hot' | 'cold'(削除しない)
);
```

### 2.8 タスクとリネージ

```sql
CREATE TABLE task_records (
  task_id      UUID PRIMARY KEY,
  cohort_id    UUID NOT NULL,
  idempotency_key TEXT,
  metadata     JSONB NOT NULL,          -- importance/difficulty/category(指定or自動分類、由来を記録)
  slot_id      UUID NOT NULL,           -- 担当スロット
  generation   INT NOT NULL,            -- 担当時点の世代 ★リネージの要
  tv_id        UUID NOT NULL,           -- 担当時点の教師ベクトル
  cycle_id     UUID,                    -- 適用中ダイナミクスの由来サイクル
  status       TEXT NOT NULL,           -- 'completed' | 'failed' | ...
  input_ref    TEXT, output_ref TEXT,   -- 原文はオブジェクトストレージ(TTL設定可)
  output_embedding vector,              -- 安全監視・散逸度入力
  requested_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ,
  UNIQUE (cohort_id, idempotency_key)
);

CREATE TABLE routing_decisions (
  task_id      UUID PRIMARY KEY REFERENCES task_records,
  candidates   JSONB NOT NULL,          -- [{slot_id, maturity, fitness, score, cluster}]
  chosen_slot  UUID NOT NULL,
  reason       JSONB NOT NULL           -- ルール適用の構造化理由(開示請求で使用)
);
```

### 2.9 安全境界・提案・承認

```sql
CREATE TABLE negative_centroids (
  centroid_id  UUID PRIMARY KEY,
  cohort_id    UUID NOT NULL,
  label        TEXT NOT NULL,           -- 'discriminatory' | 'prompt_injection' 等
  vector       vector NOT NULL,
  threshold    REAL NOT NULL DEFAULT 0.85,
  is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE proposals (                 -- FR-GV-04 (¶0228-0230)
  proposal_id  UUID PRIMARY KEY,
  slot_id      UUID NOT NULL,
  kind         TEXT NOT NULL,           -- 'rehatch_request' | 'role_change'
  rationale    JSONB NOT NULL,          -- エージェント側の根拠(損失停滞等)
  decision     TEXT,                    -- 'approved' | 'rejected' | NULL(未決)
  decision_reason JSONB,                -- 群状態との照合結果
  decided_by   TEXT,                    -- 'orchestrator' | user_id
  submitted_at TIMESTAMPTZ NOT NULL, decided_at TIMESTAMPTZ
);

CREATE TABLE approval_requests (         -- FR-GV-05
  approval_id  UUID PRIMARY KEY,
  tenant_id    UUID NOT NULL,
  action_type  TEXT NOT NULL,           -- 'rehatch' | 'dimension_expansion' | 'threshold_change'
  action_payload JSONB NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/rejected/expired
  requested_by TEXT NOT NULL, approvers JSONB NOT NULL DEFAULT '[]',
  expires_at   TIMESTAMPTZ NOT NULL
);
```

## 3. データ保持・階層化

| データ | ホット | コールド移行 | 備考 |
|---|---|---|---|
| slot_events / cohort_cycles | 13ヶ月 | オブジェクトストレージ(Parquet)へ月次移行、照会はエクスポートAPI経由 | 削除しない(NFR-SC-04) |
| probe_results | 3ヶ月 | 世代ごとに代表値へ集約後コールド化 | 埋め込み容量対策(NFR-CT-02) |
| task原文(input/output) | テナント設定TTL(既定90日) | TTL後削除(埋め込み・メタは保持) | GDPR対応(NFR-CP-03) |
| model_snapshots / knowledge_archives | 直近5世代ホット | 以降コールド階層 | 削除ではなく退避 |

## 4. 整合性・不変条件(アプリ層で強制+テストで担保)

1. `slots` はDELETE不可(DB権限+FK RESTRICT)。`cohorts.slot_count` はPhase遷移後にUPDATE不可(トリガ)
2. `slot_events` は同一 `slot_id` 内で `prev_hash` が直前イベントの `hash` に一致(挿入時検証)
3. `generation` は `REHATCH_COMPLETED` / `REHATCH_ROLLED_BACK` イベントでのみ変化
4. `task_records.generation` = 担当時点の `slots.generation`(ルーティング時に確定、事後変更不可)
5. Phase=`OPERATING` のコホートに対する `SLOT_CREATED` イベントは拒否(卵層非再入、請求項10)
6. `teacher_vectors` は追記のみ。`dimension` 減少は禁止
