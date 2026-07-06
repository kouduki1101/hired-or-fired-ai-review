# 05. API仕様書

- 版数: 1.0 (Draft for Review)
- ベースURL: `https://api.aios.example/v1`(Self-Hostedは任意)
- 形式: REST + JSON。OpenAPI 3.1 定義を一次成果物とし、本書は設計意図を示す
- 認証: `Authorization: Bearer <APIキー or OIDCトークン>`。全リクエストにテナントコンテキスト
- 冪等性: 変更系は `Idempotency-Key` ヘッダ対応
- **設計原則: スロットのDELETEエンドポイントは存在しない**(請求項2/No-Delete by Design)

---

## 1. リソース一覧

| リソース | 主な操作 |
|---|---|
| `/cohorts` | コホート作成(卵層起動)・参照・設定変更・ループ制御 |
| `/cohorts/{id}/slots` | スロット参照・ロック・休止/復帰(削除なし) |
| `/cohorts/{id}/tasks` | タスク投入(ルーティング)・結果参照 |
| `/cohorts/{id}/metrics` | 指標時系列(TV/散逸度/適合度/健全性) |
| `/cohorts/{id}/rehatch` | 手動Rehatch・履歴 |
| `/cohorts/{id}/scaling` | 次元拡張 |
| `/cohorts/{id}/probes` | プローブセット管理 |
| `/cohorts/{id}/safety` | 禁止ベクトル・隔離管理 |
| `/lineage` | 開示請求応答・監査エクスポート |
| `/proposals` | エージェント自律提案 |
| `/approvals` | 承認キュー |
| `/admin/*` | テナント・ユーザ・APIキー・Webhook |

## 2. 主要エンドポイント詳細

### 2.1 コホート作成(卵層 / Phase1) — FR-LC-01

```
POST /v1/cohorts
{
  "name": "support-agents-prod",
  "slot_count": 20,
  "adapter_kind": "anthropic_agent",
  "initial_teacher_vector": {                 // T_0 の与え方(いずれか)
    "mode": "nl_directive",                   // 'nl_directive' | 'vector' | 'probe_baseline'
    "nl_directive": "丁寧で正確なカスタマーサポート。推測で回答しない。...",
    "dimension": 1536
  },
  "seed_config": {                            // 各スロット初期構成の生成方法
    "base_system_prompt": "...",
    "diversity": 0.3                          // 初期多様性(シード摂動幅)
  },
  "cycle_interval": "PT5M",
  "ema_alpha": 0.1,
  "approval_mode": "auto"                     // 'auto' | 'manual'
}
→ 201 { "cohort_id": "...", "phase": "INITIALIZING", "slots": [ {"slot_id":"...","display_id":"001"}, ... ] }
```

- 初期化完了(K体生成+キャリブレーション)で `phase: OPERATING` へ遷移。以降このAPIでの当該コホートへのスロット追加は 409
- `POST /cohorts/{id}/slots` は**存在しない**(Phase2の追加生成禁止、請求項10)

### 2.2 タスク投入 — FR-RT

```
POST /v1/cohorts/{id}/tasks
Idempotency-Key: 7c9e...
{
  "input": { "messages": [...] },
  "metadata": {                                // 任意。未指定なら自動分類
    "importance": "high",                      // high|normal|low
    "difficulty": "hard",                      // hard|normal|easy|exploratory
    "category": "billing"
  },
  "routing": { "mode": "auto" }                // 'auto' | {'pin_slot': '...'}(要権限) | 'ensemble'(C)
}
→ 200 {
  "task_id": "...",
  "output": {...},
  "routed_to": { "slot_id": "...", "display_id": "007", "generation": 12, "cluster": "veteran" },
  "lineage_ref": "/v1/lineage/tasks/{task_id}"
}
```

- 同期(既定, タイムアウト設定可)と非同期(`Prefer: respond-async` → 202+ポーリング/Webhook)の両対応

### 2.3 指標参照 — FR-MT / FR-UI

```
GET /v1/cohorts/{id}/metrics/current
→ 200 {
  "step_no": 1842, "health": "STABLE",
  "dissipation": { "value": 0.42, "algo": "output_embedding", "thresholds": {"lower":0.2,"upper":0.7} },
  "teacher_vector": { "tv_id": "...", "dimension": 1536, "delta_norm": 0.013, "nl_directive": "..." },
  "dynamics": { "lr_correction": 1.0, "noise_amount": 0.05 },
  "fitness": { "mean": 0.81, "min": 0.55, "max": 0.93 },
  "slots": [ { "slot_id":"...", "display_id":"001", "maturity": 3200, "fitness": 0.88,
               "status":"ACTIVE", "generation": 12, "rehatched_recently": false }, ... ]
}

GET /v1/cohorts/{id}/metrics/history?from=&to=&series=dissipation,health,fitness_mean,tv_delta
GET /v1/cohorts/{id}/metrics/stream        (SSE: サイクル毎に上記currentの差分を配信)
```

### 2.4 Rehatch — FR-RH

```
POST /v1/cohorts/{id}/rehatch              // 手動指示(自動は制御ループが実施)
{
  "slot_id": "...",
  "strategy": "prompt_recompose",          // tv_init | adapter_regen | distillation | prompt_recompose
  "blend_ratio": 0.5,                      // β: 現状態と目標の混合率
  "source": { "mode": "auto" }             // 'auto'(TV+アーカイブマッチング) | {'archive_id': ...}
}
→ 202 { "rehatch_id": "...", "status": "queued" }        // approval_mode=manualなら approval_id を返す

GET  /v1/cohorts/{id}/rehatch/{rehatch_id}                // 進捗・検証結果・ロールバック有無
GET  /v1/cohorts/{id}/slots/{slot_id}/generations          // 世代系譜(各世代の由来: 戦略・継承元)
PUT  /v1/cohorts/{id}/slots/{slot_id}/lock  {"rehatch_lock": true}   // 削除保護フラグ
```

### 2.5 ループ制御・ダイナミクス — FR-LC-03 / FR-DY

```
POST /v1/cohorts/{id}/loop   {"action": "pause" | "resume" | "dry_run_on" | "dry_run_off"}
PUT  /v1/cohorts/{id}/dynamics/override   {"lr_correction": 0.5, "noise_amount": 0.0, "locked": true}
DELETE /v1/cohorts/{id}/dynamics/override   // 自動制御へ復帰(操作は監査記録)
```

### 2.6 次元拡張 — FR-SC

```
POST /v1/cohorts/{id}/scaling/expand      (approval対象)
{ "added_dims": 128, "axis_labels": ["倫理的配慮", "法務知識深度", ...] }   // labels必須・added_dims分
→ 202 { "operation_id": "...", "new_dimension": 1664 }
GET  /v1/cohorts/{id}/scaling/axes         // 価値軸レジストリ
```

### 2.7 リネージ・開示請求 — FR-GV-01〜03

```
GET /v1/lineage/tasks/{task_id}
→ 200 {
  "task_id": "...",
  "handled_by": { "slot_id": "...", "display_id": "003", "generation": 12 },
  "generation_lineage": {
    "rehatched_at": "2026-05-01T10:06:00Z",
    "strategy": "distillation",
    "teacher_vector": { "tv_id": "...", "measured_at": "...", "nl_directive_excerpt": "..." },
    "inherited_from": { "archive_id": "...", "kind": "elite_model", "archived_at": "..." }
  },
  "dynamics_at_time": { "lr_correction": 1.0, "noise_amount": 0.05 },
  "explanation": "本回答はスロット003の第12世代モデルによるものです。同世代は2026年5月1日時点の
    運用方針(教師ベクトル ...)およびアーカイブ済み優良モデルAの知識を継承して構成されました。",
  "data_disposal_note": null            // 原文破棄済みの場合はプロセス正当性説明(¶0227)
}

GET  /v1/lineage/slots/{slot_id}/history?from=&to=      // 運用履歴タイムライン(全世代)
POST /v1/lineage/export  { "cohort_id": "...", "from": "...", "to": "...", "format": "jsonl" }
→ 202 → 完了Webhook + 署名付きURL(ハッシュチェーン検証マニフェスト同梱)
```

### 2.8 自律提案 — FR-GV-04

```
POST /v1/proposals            (ServiceAccount権限: エージェント/ラッパーが呼ぶ)
{ "slot_id": "...", "kind": "rehatch_request",
  "rationale": { "val_loss_plateau_cycles": 12, "detail": "..." } }
→ 201 { "proposal_id": "...", "status": "pending" }

GET /v1/proposals/{id}
→ 200 { "decision": "rejected",
        "decision_reason": { "rule": "chaotic_freeze", "health": "CHAOTIC",
                             "message": "群が過分散状態のため新規Rehatchを凍結中" } }
```

### 2.9 安全境界 — FR-SF

```
POST /v1/cohorts/{id}/safety/negative-centroids
{ "label": "prompt_injection", "examples": [ {"text": "..."}, ... ], "threshold": 0.85 }
→ 201   // examplesから特徴量平均ベクトルを算出して登録

POST /v1/cohorts/{id}/slots/{slot_id}/quarantine     // 手動隔離
POST /v1/cohorts/{id}/slots/{slot_id}/restore        // 復旧(安全チェックポイントからのRehatchを起動)
GET  /v1/cohorts/{id}/safety/incidents
```

### 2.10 承認キュー — FR-GV-05

```
GET  /v1/approvals?status=pending
POST /v1/approvals/{id}/approve   { "comment": "..." }
POST /v1/approvals/{id}/reject    { "comment": "..." }
```

## 3. Webhook イベント(FR-EX-01)

| イベント | ペイロード要点 |
|---|---|
| `cohort.health_changed` | cohort_id, from/to(STABLE→FIXED等), dissipation |
| `slot.quarantined` | slot_id, 触発した禁止ベクトルlabel, 類似度 |
| `rehatch.completed` / `rehatch.rolled_back` | slot_id, generation, strategy, 継承元 |
| `approval.requested` | action_type, payload要約, 期限 |
| `cohort.stabilization_point` | step_no, スナップショットarchive_id |
| `dynamics.adjusted` | lr_correction, noise_amount, 理由(health) |

- 署名: `X-AIOS-Signature: sha256=...`(HMAC、シークレットはテナント毎)。リトライ: 指数バックオフ24時間

## 4. SDK(高水準API)

```python
# Python SDK 例
from aios import Client
aios = Client(api_key=...)

cohort = aios.cohorts.create(name="support", slot_count=20, adapter="anthropic_agent",
                             directive="丁寧で正確なサポート...", approval_mode="manual")

result = cohort.tasks.run(messages=[...], importance="high")   # ルーティング込み推論
print(result.routed_to.display_id, result.output)

lineage = aios.lineage.task(result.task_id)                    # 開示請求応答
cohort.metrics.stream(on_cycle=lambda m: print(m.health))      # SSE購読

# エージェント側ラッパー(自律提案)
aios.proposals.submit(slot_id=..., kind="rehatch_request", rationale={...})
```

- TypeScript SDKも同等API。両SDKはOpenAPI生成クライアント+手書き高水準層の2層構成(NFR-MT-03)

## 5. エラー規約

- RFC 9457 (Problem Details)。`type` にエラーカタログURL、`extensions.aios_code` に機械可読コード
- 代表コード: `phase_locked`(Phase2でのスロット追加等) / `no_delete`(削除系操作) / `approval_required` /
  `slot_locked` / `quarantined` / `idempotency_conflict` / `budget_exceeded`(NFR-CT-01)
- レート制限: 429 + `Retry-After`。テナント別限度はプラン依存
