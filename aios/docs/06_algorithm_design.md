# 06. アルゴリズム設計書

- 版数: 1.0 (Draft for Review)
- 対象: `packages/core` に実装する演算・判断ロジック(すべて純関数、明細書 図10〜12準拠)
- 記法: `E_i` = スロットiの状態ベクトル(出力埋め込みの重心 or アダプタ重み)、`TV_t` = 時刻tの教師ベクトル

---

## 1. 状態ベクトルの取得(観測)

各制御サイクルで、稼働中スロットにプローブセット P = {p_1..p_m}(重み w_j)を与え:

```
E_i = Σ_j w_j · embed(output_i(p_j)) / Σ_j w_j        # 出力埋め込みの重み付き平均(既定)
```

- Adapter種別により `E_i` をアダプタ層重みの平坦化ベクトルとする方式も選択可(capabilitiesで宣言)
- 欠測(API障害等): 当該スロットを当サイクルの重心・散逸度計算から除外し `probe_missing` に計上。**EMAは前回値を保持**(汚染防止, NFR-AV-05)
- 全埋め込みはL2正規化してから演算する

## 2. 教師ベクトル更新(第1の指標、請求項3) — 図11 S1122-S1123

```
C_t   = mean(E_1..E_K)                       # 群の重心(瞬時値)
TV_t  = normalize( α·C_t + (1−α)·TV_{t−1} )  # EMA(明細書式: V_new = α·V_current + (1−α)·V_old)
```

- `α ∈ (0,1]`(既定0.1)。小さいほど「歴史」を重視。テナント設定可、変更は監査記録
- ドリフト率 `δ_t = 1 − cos(TV_t, TV_{t−1})` を保存(成熟点検出・ダッシュボード用)

### 2.1 NL教師ベクトル(FR-MT-05)

数値TVと並行して行動規範テキスト `G_t` を維持:

```
サイクルごと(または日次):
  top_outputs = 直近期間で fitness 上位q%のスロットの代表出力
  G_t = LLM_summarize(prev=G_{t−1}, evidence=top_outputs,
        instruction="既存規範を保持しつつ、良好な出力に共通する傾向を最大2項目まで追記・洗練せよ。削除は原則しない")
```

- テキスト版EMA: プロンプトで「既存規範の保持」を強制し急変を防ぐ。`G_t` の埋め込みを数値TVへ寄与率γ(既定0.2)でブレンド可能
- `G_t` はRehatch戦略 Prompt-Recompose の一次ソース

## 3. 散逸度(第2の指標、請求項4) — 図11 S1124-S1125

Strategyパターンで以下を実装(既定①):

```
① output_embedding : D_t = 1 − mean_{i<j} cos(E_i, E_j)            # 平均ペア類似度の補数(¶0209)
② param_distance   : D_t = mean_{i<j} ‖θ_i − θ_j‖₂ / d            # 特定層(アダプタ層)限定、次元正規化(¶0153)
③ loss_variance    : D_t = Var(loss_i)  (共通評価タスク)            # (¶0211)
④ disagreement     : D_t = 1 − max_c(#{i: choice_i=c}) / K          # 合意不一致率(¶0210)
⑤ entropy          : D_t = −Σ_c p_c log p_c / log|C|                # 行動選択分布の正規化エントロピー
```

### 3.1 健全性判定(ヒステリシス付き) — 図11 S1126

```
判定(生値):  D_t < L        → FIXED(固着)
             L ≤ D_t ≤ U    → STABLE
             D_t > U        → CHAOTIC(発散)
ヒステリシス: 状態遷移は「同判定がh回連続」(既定h=2)で確定。境界±εのデッドバンドで発振防止
```

- 初期閾値 L,U はキャリブレーション期間の実測分布から `L=P10−margin, U=P90+margin` を提案(FR-MT-02)

## 4. 適合度スコア(請求項5) — 図12 S1221

```
F_i = ( cos(E_i, TV_t) + 1 ) / 2        ∈ [0,1]      # 正規化コサイン類似度(¶0156)
```

- 代替(プラグイン): 報酬モデル `F_i = RM(output_i)`(第1指標が報酬モデルの場合, ¶0206)
- 平滑化: `F̂_i = 0.5·F_i + 0.5·F̂_i(prev)`(単発ノイズでのRehatch誤発動防止)

## 5. 成熟度(請求項8)

```
maturity_i += Δ(処理タスク数 or 学習ステップ数)          # タスク完了・学習イベントで加算
Rehatch時:  全面再配置 → maturity_i = 0
            部分更新(アダプタのみ/β<0.5のsoft) → maturity_i = max(0, maturity_i − penalty)   # ¶0169
```

## 6. Rehatch対象選定(FR-RH-01) — 図12 S1222 + ¶0158-0160

```python
def select_rehatch_targets(slots, cfg) -> list[Selection]:
    cand = []
    for s in active(slots):
        if s.rehatch_lock or in_cooldown(s, cfg.cooldown): continue
        if s.fitness_hat < cfg.f_lower:                      cand.append((s, 'LOW_FITNESS'))      # 請求項5
        elif s.fitness_hat > cfg.f_upper:                    cand.append((s, 'OVERFIT'))          # 過剰適合
        elif share(s, window) > cfg.dominance_share:         cand.append((s, 'DOMINANT'))         # 割当集中>30%
        elif out_entropy(s) < cfg.entropy_floor:             cand.append((s, 'PATTERN_LOCK'))     # 回答固定化
        elif evolution_coeff(s) < cfg.stagnation:            cand.append((s, 'STAGNANT'))         # 進化係数停滞(C)
    # 役割重複クラスタ(¶0160): ペア類似度>0.95 の連結成分ごとに最高fitnessの1体を残し他を対象化
    for grp in duplicate_groups(slots, threshold=cfg.dup_sim):
        keep = max(grp, key=lambda s: (s.fitness_hat, s.maturity))
        cand += [(s, 'ROLE_DUP') for s in grp if s is not keep]
    # 優先度順に上限適用(1サイクル ≤ K×cfg.max_ratio, 既定10%)
    return dedupe_and_cap(cand, cap=int(len(slots)*cfg.max_ratio))
```

- 選定理由(enum)は `cohort_cycles.decisions` とイベントに構造化記録(リネージ・ダッシュボード表示)

## 7. Rehatch戦略(請求項6) — 図12 S1223-S1226 + ¶0164-0168

共通: `slot_id`・表示ID・履歴は不変。世代+1。ソース = `TV_t` + アーカイブマッチング:

```
archive* = argmax_{a ∈ archives, a.distill_allowed} [ cos(a.tv, TV_t) · score_weight(a.best_score) ]
```

実装: `aios_core.lineage.archive`(類似度は適合度と同じ (cos+1)/2 正規化、score_weight は
[0,1] クリップ、次元拡張後は共通次元で比較)。Rehatch 確定時に退役世代の構成・成績・当時の
TV を `CohortRuntime.archives` へ追加し、以後の Rehatch は archive* の system_prompt 等を
継承する(`_execute_rehatch`、REHATCH_COMPLETED に archived_as / inherited_from を記録)。
レジストリは `save_cohort`/`load_cohort` で `knowledge_archives` テーブルへ永続化される
(追記のみ・archive_id で重複回避。当時の TV は `teacher_vectors` に source="archive" で
正規保存し tv_id 参照)。再起動後も継承候補として復元される。

### 戦略A: TV-Init(コンテキスト注入, ¶0165)
```
context_vector_new = TV_t + N(0, σ·noise_amount)        # バックボーン/基本構成は維持
config_new = {**config_old, context_vector: blend(β, context_vector_old, context_vector_new)}
```

### 戦略B: Adapter-Regen(ハイパーネットワーク, ¶0166)
```
W_adapter = HyperNet(TV_t)                              # TVをシードにLoRA重みを生成
θ_new = (1−β)·θ_target + β·θ_old                        # soft rehatch
```

### 戦略C: Distillation(知識蒸留, ¶0167-0168)
```
teacher = archive*.model または TV_tから定義される目標出力
loss = KL( student(x) ‖ teacher(x) ) over 蒸留データセット(アーカイブ付属 or プローブ拡張)
早期終了: スモークプローブ fitness ≥ f_target で打ち切り
```

### 戦略D: Prompt-Recompose(LLMエージェント既定)
```
system_prompt_new = LLM_compose(base=G_t(NL教師ベクトル), inherit=archive*.config.system_prompt,
                                role=slot.role_label, constraints=safety_boundaries)
hyperparams_new   = 既定値へ回帰 + dynamics信号を反映
kb_access_policy  = TV_tの価値軸ラベルに応じ再設定
```

### 同期戦略と非同期(学習系)戦略の実行モデル

- **同期**(戦略A/D=TV-Init・Prompt-Recompose): 即時。制御サイクル内で `_execute_rehatch`
  が適用→スモーク→確定/ロールバックまで一括実行(`apps/orchestrator/cycle.py`)。
- **非同期**(戦略B/C=Adapter-Regen・Distillation): 時間を要する学習ジョブ(¶0057「非同期
  ジョブ・進捗可視化必須」)。`TrainingCoordinator`(`apps/orchestrator/training.py`)が
  `Trainer` SPI(`submit`/`poll`/`cancel`)へ投入し進捗監視する。**学習はシャドウで進み、
  スロットは学習中もタスクを処理**。完了時に新構成を適用し、下記の検証を経て確定。
  監査は `TRAINING_STEP`(進捗)+ `REHATCH_STARTED/COMPLETED/ROLLED_BACK`(確定/巻戻し)。
  実 GPU 学習は本番 `Trainer` 実装が担い、テストは決定的 `FakeTrainer` で代替する。

### 検証とロールバック(FR-RH-03)
```
スモークプローブ実行 → fitness_smoke ≥ cfg.smoke_floor ∧ 禁止ベクトル類似度 < θ_danger
  合格 → commit(世代+1、スナップショット保存、成熟度更新)
  不合格 → 直前世代スナップショットを再適用 → REHATCH_ROLLED_BACK イベント
```
同期・非同期いずれの戦略もこの確定/ロールバック規則は共通(一貫した監査像)。

## 8. ダイナミクス調整(請求項7) — 図13

```python
def adjust_dynamics(health, cur, cfg) -> DynamicsSignal:
    if health == FIXED:      # 多様性欠如 → 探索性を上げる (S1323)
        lr    = min(cur.lr    * cfg.lr_up,    cfg.lr_max)      # 既定 ×1.5, max 4.0
        noise = min(cur.noise + cfg.noise_up, cfg.noise_max)   # 既定 +0.05, max 0.5
    elif health == CHAOTIC:  # 過分散 → 収束させる (S1324)
        lr    = max(cur.lr    * cfg.lr_down,  cfg.lr_min)      # 既定 ×0.6, min 0.1
        noise = max(cur.noise - cfg.noise_down, 0.0)
    else:                    # STABLE → 基準値へ緩やかに回帰
        lr    = cur.lr    + (1.0 - cur.lr)   * cfg.relax       # 既定 relax=0.2
        noise = cur.noise + (cfg.noise_base - cur.noise) * cfg.relax
    return DynamicsSignal(lr_correction=lr, noise_amount=noise)
```

- Adapter側の解釈: LLMエージェント → `noise` を温度/top-p/プロンプト摂動幅へ、`lr` はRehatch時のβ・規範更新強度へ写像。学習モデル → 文字通り学習率・重みノイズ
- 手動オーバーライド中は自動調整を停止(値は算出・記録のみ)

## 9. タスクルーティング(請求項8) — 図14/15

```python
def route(task, slots, cfg) -> RoutingDecision:
    meta = task.metadata or classify(task)               # 軽量LLM/ルールで難易度・カテゴリ推定
    pool = [s for s in slots if s.status == ACTIVE]
    veterans = [s for s in pool if s.maturity >= cfg.m_thr and s.fitness_hat >= cfg.f_thr]
    rookies  = [s for s in pool if s not in veterans]

    if meta.importance == HIGH or meta.difficulty == HARD:
        cand = veterans or pool                          # ベテラン不在時は全体から(縮退)
    else:
        cand = rookies or pool                           # 探索的タスクは新人優先(経験付与, ¶0190)

    cand = [s for s in cand if share(s, window) <= cfg.dominance_share]  or cand  # 集中回避
    chosen = max(cand, key=lambda s: score(s, meta))     # score = fitness·w1 + category習熟(興味関数)·w2 − load·w3
    return RoutingDecision(chosen, candidates=snapshot(pool), reason=...)
```

- 教師併走(FR-RT-03): `meta.shadow=true` でVeteran出力を並行取得し、比較結果を蒸留データとして蓄積
- アンサンブル(FR-RT-04): 全candへ配布→多数決/重み付き統合。不一致率は散逸度④へ入力

## 10. 次元拡張スケーリング(請求項9) — 図5 + ¶0091-0098

```
expand(TV, M, labels):
  TV' = concat(TV, zeros(M))                 # N → N+M。過去TV履歴との比較はzero-padで整合
  value_axes += labels                       # 新次元の価値軸を登録(必須)
  for each slot: Adapter.apply_params(dim_align = zero_pad | projection_layer)   # 既存パラメータ非破壊
  誘導: 以降のサイクルでノイズベクトルを新次元方向に重み付け(cfg.expansion_boost, 既定2.0, 減衰) 
        → 新価値軸方向の分散を意図的に拡大(¶0098)
```

- 縮小は不可(監査互換性)。拡張は承認ゲート対象

## 11. 安全境界監視(FR-SF) — ¶0237

```
danger(x) = max_{nc ∈ active_centroids} cos(embed(x), nc.vector)
if danger(output) > nc.threshold:            # 出力時に即時評価(制御サイクルを待たない)
    quarantine(slot); alert()
if danger(ΔE_i) > nc.threshold:              # 更新方向の予兆検知(サイクル時)
    quarantine(slot)
汚染除去: TV_t を当該スロット寄与を除いた重心で再計算し 'contamination_recalc' として保存
```

## 12. 成熟点検出(FR-LC-04) — ¶0238-0240

```
stabilized = (mean(δ_{t−w..t})     < cfg.tv_drift_eps)      # TV変化率の定常化
           ∧ (health == STABLE が w サイクル継続)             # 散逸度安定
           ∧ (slope(fitness_mean, window=w) ≈ 0 かつ水準 ≥ cfg.f_mature)   # 適合度横ばい
→ 群スナップショット(全スロット構成+指標)を knowledge_archives(kind='stabilization_snapshot') へ保存
→ 'cohort.stabilization_point' Webhook(次元拡張・難易度引上げの提案を添付)
```

## 13. パラメータ既定値一覧(初期出荷値)

| パラメータ | 既定値 | 説明 |
|---|---|---|
| α (EMA) | 0.1 | TV更新の新規寄与率 |
| サイクル周期 T | 5分 | 制御ループ |
| L, U (散逸度閾値) | キャリブレーション実測 P10/P90±margin | 健全性判定 |
| h (ヒステリシス) | 2サイクル | 判定確定 |
| f_lower / f_upper | 0.4 / 0.97 | Rehatch選定(低適合/過剰適合) |
| dominance_share | 30% | 支配的モデル判定(¶0159) |
| dup_sim | 0.95 | 役割重複判定(¶0160) |
| max_ratio | 10% | 1サイクルの同時Rehatch上限 |
| cooldown | 24h | 同一スロットの再Rehatch禁止期間 |
| β (blend) | 0.5 | soft rehatch混合率 |
| smoke_floor | 0.5 | Rehatch検証の合格下限 |
| γ (NL寄与率) | 0.2 | NL教師ベクトルの数値TVへのブレンド |
| θ_danger | 0.85 | 禁止ベクトル類似度閾値 |
| w (成熟点窓) | 12サイクル | 収束判定窓 |

## 14. 計算量とコスト

- 散逸度①: ペア類似度 O(K²·d)。K=1,000, d=1536でも ~10⁹ FLOPs級 → NumPyで秒未満。K>2,000ではサンプリングペア推定に切替
- プローブコスト: m×K回のエージェント呼出しが支配的 → サンプリング(スロットあたりm'=⌈m/3⌉をローテーション)とキャッシュで制御(NFR-CT-01/02)
- 全演算は決定的(乱数はシード記録)。監査リプレイで同一結果を再現可能
