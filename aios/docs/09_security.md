# 09. セキュリティ設計・脅威モデル

- 版数: 1.0
- 適用範囲: AIOS Control Plane(`apps/api` / `apps/orchestrator` / `packages/*` / `apps/dashboard`)
- 関連: NFR-SE(02)、API仕様(05)、データモデル(04)、`docs/security/pentest_scope.md`

本書は第三者ペネトレーションテストの前提資料であり、実装済みのセキュリティ統制と
残存リスクを明示する。統制はコードにマップして参照可能にする。

---

## 1. 資産と信頼境界

| 資産 | 機微度 | 保護目標 |
|---|---|---|
| 教師ベクトル・散逸度・適合度などの運用指標 | 中(営業秘密) | 機密性・完全性 |
| スロットのモデルパラメータ/スナップショット参照 | 高 | 機密性・完全性 |
| 監査イベント連鎖(リネージ) | 高(証跡) | **完全性(改竄検知)**・可用性 |
| APIキー / OIDC トークン / Webhook シークレット | 高(資格情報) | 機密性 |
| テナント境界(マルチテナント分離) | 高 | 機密性(越境防止) |

信頼境界:
1. **公開網 → API**(認証境界)。AuthMiddleware(`apps/api/auth.py`)で遮断。
2. **テナント間**。ContextVar `current_tenant` により Store 層で分離(越境は 404)。
3. **API → 外部 Webhook**。送信データは HMAC 署名(`notify.py`)。
4. **制御プレーン → モデルアダプタ**(SPI 境界)。アダプタは能力申告に基づき呼び出す。

---

## 2. STRIDE 脅威分析と統制

| # | 脅威(STRIDE) | シナリオ | 統制 | 実装 |
|---|---|---|---|---|
| S1 | なりすまし | 資格情報なしで API 操作 | APIキー(X-API-Key)/ OIDC Bearer 検証 | `auth.py`, `oidc.py` |
| S2 | なりすまし | 失効/改竄トークンの受理 | `exp`/`iss`/`aud` 検証・署名検証(HS256/RS256) | `oidc.py::OidcVerifier.verify` |
| T1 | 改竄 | 監査履歴の事後改変 | SHA-256 ハッシュ連鎖 + 検証、**削除API不在(設計)** | `lineage/events.py`, `lineage/replay.py::verify_chain`, 契約テスト |
| T2 | 改竄 | Webhook ペイロードの中間者改変 | HMAC-SHA256 署名(`X-AIOS-Signature`) | `notify.py::sign_payload` |
| R1 | 否認 | 「その操作はしていない」 | 追記専用イベント+主体(Principal)+世代の記録 | イベントストア、開示請求応答 |
| I1 | 情報漏洩 | 他テナントのコホート/履歴の閲覧 | テナントスコープ(越境 404) | `store.py`, テナント結合テスト |
| I2 | 情報漏洩 | シークレットの応答返却 | Webhook シークレットは応答に含めない(NFR-SE-04) | `routers/admin.py` |
| I3 | 情報漏洩 | ブラウザ経由の各種漏洩 | 厳格セキュリティヘッダ(CSP/HSTS/nosniff/no-store) | `security.py` |
| D1 | サービス拒否 | 認可の抜けによる高コスト操作乱用 | RBAC(書込=OPERATOR、管理=ADMIN)+ レート制限(下記残存) | `rbac.py` |
| E1 | 権限昇格 | viewer が書込/承認を実行 | 集中ポリシー `required_role(method,path)` を全経路で強制 | `auth.py::dispatch`, `rbac.py` |
| E2 | 権限昇格 | 定常運用中のスロット増設(請求項10違反) | Phase ロック+スロット追加 409 | `runtime.py::guard_hatchery`, 契約テスト |

---

## 3. OWASP API Security Top 10 (2023) 対応

| リスク | 状況 | 備考 |
|---|---|---|
| API1 Broken Object Level Auth | 対応 | 全オブジェクトをテナントで絞込。越境 404 |
| API2 Broken Authentication | 対応 | APIキー / OIDC(署名・exp・aud・iss) |
| API3 Broken Object Property Level Auth | 部分 | 応答はレスポンスモデルで明示(過剰露出抑制)。シークレット非返却 |
| API4 Unrestricted Resource Consumption | 対応 | テナント単位トークンバケット(`ratelimit.py`、AIOS_RATE_LIMIT_RPS)。分散は前段/共有ストアへ差替 |
| API5 Broken Function Level Auth | 対応 | RBAC ロール階層で機能単位に制御 |
| API6 Unrestricted Access to Sensitive Business Flows | 部分 | 承認ワークフロー(manual)で高影響操作をゲート |
| API7 SSRF | 対応 | Webhook URL は ADMIN のみ登録可 + `netguard.py` で内部IP遮断/許可リスト。解決不能名は egress 制御で補完 |
| API8 Security Misconfiguration | 対応 | セキュリティヘッダ、CORS 明示、dev モードは非既定 |
| API9 Improper Inventory Management | 対応 | `/v1` バージョニング、OpenAPI 自動生成、SDK CHANGELOG |
| API10 Unsafe Consumption of APIs | 対応 | 依存は `security-audit` CI(pip-audit)で継続監査 |

---

## 4. サプライチェーン

- 依存は uv ロックファイルで固定。CI の `security-audit` ジョブが `pip-audit` で
  既知脆弱性を毎回検査(現状: 52 依存・既知脆弱性 0)。
- SDK 配布は PyPI Trusted Publishing(OIDC)でトークンレス、改竄経路を削減。

---

## 5. 実装済みハードニングと残存リスク

### 実装済み(当初「残存」から昇格)

1. **レート制限(API4)** — テナント単位トークンバケット(`ratelimit.py`)。`AIOS_RATE_LIMIT_RPS`
   /`AIOS_RATE_LIMIT_BURST` で有効化。超過は 429 + `Retry-After`。死活監視は非対象。
   分散構成では前段(Ingress)または共有ストア実装へ差し替える第一防御線。
2. **Webhook SSRF ガード(API7)** — `netguard.py` が登録時に URL を検証。IP リテラル/
   名前解決結果がループバック・RFC1918・リンクローカル(169.254.169.254 等)・予約
   に該当すれば 422。既定 https のみ。`AIOS_WEBHOOK_ALLOWED_HOSTS` で許可リスト強制。

### 残存(次期 / 運用設計)

3. **解決不能ホスト名の SSRF** — DNS 解決に失敗するホスト名は内部と断定できず許可する。
   実運用ではコンテナ/ネットワークのエグレス制御(NetworkPolicy 等)で補完する。
4. **レート制限の分散一貫性** — 現状はプロセス内。マルチレプリカでは前段集約か
   共有ストア(Redis 等)実装へ。
5. **監査ログの外部 WORM 保管** — ハッシュ連鎖で改竄検知は可能だが、削除耐性のある
   外部ストレージへの複製は運用設計事項。
6. **秘密管理** — 本番は External Secrets/KMS 前提(Helm は `existingSecret` 対応済)。

これらは `docs/security/pentest_scope.md` の「重点確認項目」に反映する。
