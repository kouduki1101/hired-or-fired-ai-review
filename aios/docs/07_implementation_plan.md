# 07. 実装計画書(フェーズ・手順・Definition of Done)

- 版数: 1.0 (Draft for Review)
- 体制想定: バックエンド2〜3名、フロント1名、SRE1名(兼務可)。期間はこの体制での目安
- 原則: 各フェーズ末に「動くもの+請求項保証テスト green」を必須とする。縦切り(エンドツーエンドで薄く通す)を優先

---

## フェーズ概観

| フェーズ | 内容 | 期間目安 | 出口(マイルストーン) |
|---|---|---|---|
| P0 | 基盤整備(リポジトリ・CI・骨格) | 2週 | `docker compose up` で空のAPI+DB+ダッシュボードが起動 |
| P1 | コア制御ループ(MVP) | 6週 | **M1: 特許請求項1〜7,10の最小実施**。20体のLLMエージェント群で固着→自動Rehatch復旧のデモ |
| P2 | ルーティング+ダッシュボード | 5週 | **M2: 請求項8実施+図16ダッシュボード完成**。デザインパートナー導入可能(Private Beta) |
| P3 | ガバナンス・安全・スケーリング | 5週 | **M3: 請求項9実施+開示請求API+Safety Boundary**。監査デモ可能 |
| P4 | 商用化(マルチテナント・SLA・課金) | 6週 | **M4: GA**。SaaS+Self-Hosted出荷 |
| P5 | 拡張(蒸留/LoRA・拡張指標・アドオン) | 継続 | GA+1以降 |

---

## P0: 基盤整備(2週)

### 手順
1. モノレポ初期化(`08_project_structure.md` の骨格を生成、uv/pnpm workspace設定)
2. `packages/common`: 設定・構造化ログ・OTel計装・エラー型
3. `packages/storage`: PostgreSQL+pgvector接続、Alembic初期マイグレーション(`04_data_model.md` §2.1-2.3 のみ)
4. `apps/api`: FastAPI骨格+認証ミドルウェア(APIキーのみ)+ヘルスチェック
5. `infra/docker-compose.yml`(postgres+pgvector, redis, minio, api, dashboard雛形)
6. CI(ci.yml): ruff/mypy strict/pytest/import-linter/pnpm lint+test。security.yml(SCA)
7. ADRの運用開始(ADR-001: イベントソーシング採用、ADR-002: Redis Streams採用 等)

### DoD
- [ ] `make dev` で全サービス起動、`make test` がCIと同一で通る
- [ ] import-linterで `core` の依存ゼロ規約が強制されている

## P1: コア制御ループ(6週) — 請求項1,2,3,4,5,6,7,10

**目標デモ**: LLMエージェント20体のコホートを作成 → 意図的に全員を同質化(固着注入) → 散逸度がFIXED判定 → ノイズ増加+低適合スロットのRehatch(Prompt-Recompose) → STABLE復帰。全過程がイベントに記録され、slot_idと履歴が途切れないこと。

### 手順(依存順)
1. **core/metrics**(1週): teacher(EMA)/dissipation①/fitness/maturity を純関数+property-based testで実装
   (`06_algorithm_design.md` §1-5。数値安定性: 正規化・欠測除外を含む)
2. **core/policy**(1週): health(ヒステリシス)/rehatch_select(LOW_FITNESS+上限+cooldown)/dynamics を実装(§3.1, 6, 8)
3. **core/lineage**: イベント型・ハッシュチェーン・replay(§2.3の不変条件をテストで固定)
4. **storage**: event_store(挿入時チェーン検証)、projections、スナップショット保存(minio)
5. **adapters**(1.5週): SPI確定 → `AnthropicAgentAdapter`(invoke/get_state/apply_params/apply_dynamics)
   + `embeddings`(Anthropic/ローカル) + conformanceキット最小版
   ※LLM API未接続でも開発できる `FakeAdapter`(決定的挙動)を先に作り、以降の全テストの土台にする
6. **orchestrator**(1.5週): phase_fsm(hatchery含む)→ cycle(Snapshot→Probe→Compute→Dynamics→Select→Actuate→Persist)
   → dry-run → recovery。ProbeWorker/MetricsWorker/RehatchWorker(戦略: Prompt-Recompose, TV-Init)
7. **api**: cohorts作成(卵層)/metrics参照/rehatch手動+lock/loop制御(§05 2.1, 2.3, 2.4, 2.5)
8. **e2e**: `test_lifecycle.py`(上記デモの自動化)+ `test_claims.py` 初版(請求項1-7,10)

### DoD
- [ ] 目標デモがe2eで再現、`test_claims.py` green
- [ ] Rehatch後: slot_id不変・generation+1・全世代履歴照会可・ロールバック動作
- [ ] Phase2で hatchery 再入不可(APIは409、内部呼出しはフェーズガード例外)
- [ ] スロットDELETE不存在の契約テスト
- [ ] core カバレッジ ≥ 90%、監査リプレイで同一指標を再現(乱数シード記録)

## P2: ルーティング+ダッシュボード(5週) — 請求項8

### 手順
1. **core/policy/routing**(1週): 分類(メタデータ/軽量LLM)→クラスタ→スコアリング→集中回避(§06 9)
2. **api/tasks**(1週): 同期/非同期投入、Redisキャッシュ経由の低レイテンシ経路、routing_decision記録、冪等キー
3. **dashboard**(2.5週): 図16の6領域(StatusHeader/DissipationMeter/TrendChart/DynamicsMonitor/SlotTiles/EventLog)
   + SSEストリーム + ループ操作/設定UI(FR-UI-07)。dataviz規約(3ゾーンは色+形状+ラベル)
4. **notify**: Webhook(署名・リトライ)+Slack/メール
5. **load test**: ルーティング p95 < 50ms / イベント 1,000/s(k6, NFR-PF-01/05)

### DoD
- [ ] 高重要度→Veteran、探索的→Rookie の割当がe2eで検証可能、決定理由が照会できる
- [ ] ダッシュボードで固着→復旧の全過程がリアルタイム可視化される
- [ ] 負荷目標達成。Private Beta顧客へ導入手順書(quickstart)提供

## P3: ガバナンス・安全・スケーリング(5週) — 請求項9+変形例(4)(5)(6)(9)(10)

### 手順
1. **lineage API**(1.5週): 開示請求応答(説明文生成テンプレート+破棄済みデータの代替説明)、
   スロット履歴タイムライン、監査エクスポート+ハッシュ検証ツール(FR-GV-01〜03)
2. **safety**(1.5週): negative_centroids登録(事例→重心算出)、safety_worker(出力時即時照合→隔離)、
   復旧Rehatch、TV汚染除去再計算(FR-SF-01〜03)
3. **scaling**(1週): 次元拡張(zero-pad+価値軸レジストリ+新次元分散誘導)、無停止動作確認(FR-SC)
4. **proposals/arbitration**: 自律提案API+群状態照合による承認/否認(FR-GV-04)
5. **approvals**: 承認ワークフロー(Rehatch/次元拡張/閾値変更)(FR-GV-05)
6. **stabilization**: 成熟点検出+スナップショット+Webhook(FR-LC-04)

### DoD
- [ ] 監査シナリオe2e: タスクID→3秒以内に世代系譜・当時TV・継承元を提示(NFR-PF-03)
- [ ] 注入攻撃事例→隔離→安全チェックポイント復旧のe2e(`test_safety.py`)
- [ ] 次元拡張が運用無停止で完了し、旧履歴との比較が保たれる
- [ ] `test_claims.py` が請求項1〜10全カバー

## P4: 商用化(6週) — GA

### 手順
1. **マルチテナント強化**: RLS+二重チェック、テナント別KMS鍵、公平スケジューリング(NFR-SE-02)
2. **認証**: OIDC SSO、RBAC 5ロール、管理操作監査(FR-TN-02)
3. **課金計測**: スロット/プローブ/タスク/ストレージのメータリング+エクスポート(FR-TN-03)、予算上限(NFR-CT-01)
4. **SRE**: Helm本番化、HPA、SLO計測(99.9%)、runbook、バックアップ/リストア演習、ゼロダウンタイムアップグレード検証
5. **SDK公開**: Python/TS(OpenAPI生成+高水準層)、ドキュメントサイト、examples
6. **セキュリティ**: 第三者ペンテスト→修正(NFR-SE-07)、コンプライアンス文書(ISO42001マッピング, NFR-CP-02)
7. **料金・ライセンス**: 特許表示、EULA、SaaS利用規約

### DoD(GA判定基準)
- [ ] NFR全項目の計測値がターゲット内(性能・可用性・セキュリティのエビデンス揃い)
- [ ] デザインパートナー2社以上で30日安定稼働(制御ループ無人運転)
- [ ] インストール(Self-Hosted)がドキュメントのみで完了することを社外検証

## P5: 拡張(GA後、優先度順)

1. `LoraPeftAdapter` + Adapter-Regen(HyperNet)+ Distillation戦略(FR-RH-02の残り)【請求項6の蒸留系を強化】
2. 拡張指標パック(興味関数・認知方向・進化係数)+ルーティング高度化(FR-MT-04)
3. アンサンブルモード(FR-RT-04)、教師併走の蒸留データ活用(FR-RT-03)
4. ERP/HCMアドオン(FR-EX-02)、NATS JetStream移行(スケール)、セル分割
5. オンデバイス/エッジエージェント対応の設計検討(¶0242)

---

## リスクと対応

| リスク | 影響 | 対応 |
|---|---|---|
| 出力埋め込みベースの指標が実運用で群の異常を捉えられない | 製品価値の根幹 | P1でFakeAdapter+合成シナリオ(固着/発散/汚染)のベンチを先行作成し、指標の検出力を定量評価。散逸度①以外への切替をStrategyで担保 |
| プローブコスト(LLM API課金)が想定超過 | 原価率悪化 | サンプリング・キャッシュ・予算上限(NFR-CT)をP1から組込み。コストダッシュボードをP2で提供 |
| Rehatchが顧客エージェントの品質を一時劣化させる | 顧客信頼 | スモーク検証+自動ロールバック(P1)、承認モード(P3)、soft rehatch(β)既定0.5 |
| 特許構成要件との乖離(実装が請求項を満たさなくなる) | 特許実施品の主張不能 | `test_claims.py` をCI必須ゲート化。請求項トレーサビリティマトリクス(00_overview §5)をリリース毎に更新・レビュー |
| K²計算のスケール限界 | 大規模テナント | K>2,000でサンプリング推定へ自動切替(06 §14)。SLOをスロット数条件付きで定義 |

## 開発プロセス規約

- 全PRは仕様書(本ドキュメント群)の該当FR/NFR IDをdescriptionに記載
- アルゴリズム変更は必ずADR+`06_algorithm_design.md` の改版を伴う
- リリース判定会で請求項トレーサビリティマトリクスを確認(法務同席は年2回)

---

## 進捗記録(2026-07-06)

| フェーズ | 計画 | 実績 |
|---|---|---|
| P0 | 2週 | ✅ 完了(uvモノレポ・CI・compose) |
| P1 | 6週 | ✅ 完了(M1デモ=固着→自動復旧をe2e化。蒸留/LoRAはP5へ計画どおり繰延) |
| P2 | 5週 | ✅ 完了(M2=図16ダッシュボード実画面検証済み。ルーティングp95計測は未実施) |
| P3 | 5週 | ✅ 完了(M3=開示請求API・監査エクスポート・安全境界・次元拡張・承認ワークフロー) |
| P4 | 6週 | ✅ 完了。前半(課金計測・APIキー認証・テナント分離)に加え、後半(Alembic、Helm、CI強化、OIDC/RBAC、負荷試験、ペンテスト準備、SDK公開手続き)を実装 |
| P5 | 継続 | 未着手(蒸留/LoRA 等の学習系 Rehatch、OpenTelemetry 実配線) |

品質状態: Pythonテスト196件+API契約テスト(請求項1〜10保証)green、1 skipped(PG結合はCIで実走)。
lint(ruff)green、依存の既知脆弱性 0(pip-audit)。

### P4後半の実績(2026-07-06)

| 項目 | 実装 | 検証 |
|---|---|---|
| Alembic マイグレーション | `packages/storage/migrations` | ドリフトゼロ検証(SQLite/PG) |
| CI 強化 | helm lint/template + PG 結合(pgvector) | GitHub Actions で実走 green |
| OIDC SSO + RBAC | `apps/api/{oidc,rbac,auth}.py` | `test_oidc_rbac.py`(HS256/RS256、403/401) |
| セキュリティハードニング | `apps/api/security.py`(ヘッダ) | `test_security_headers.py` |
| 負荷試験 / 実測 | `loadtest/{benchmark,locustfile}.py` | ルーティング p95≈3ms(NFR-PF-01 充足) |
| ペンテスト準備 | `docs/09_security.md`、`docs/security/pentest_scope.md`、`.github/SECURITY.md` | STRIDE + OWASP API Top10、`security-audit` CI |
| SDK 公開手続き | `packages/sdk-python`(メタデータ/README/CHANGELOG/py.typed)、`sdk-publish.yml` | `uv build` + `twine check` PASSED、Trusted Publishing |

残論点(要ユーザー判断): SDK ライセンス(現状 Proprietary 明記。client SDK として
MIT/Apache 等への変更を検討可)、レート制限・Webhook 許可リスト(脅威モデル §5 の
残存リスク、次期実装)。
