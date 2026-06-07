# Hired or Fired MVP 仕様書

作成日: 2026-06-04

## 1. プロダクト概要

### アプリ名

Hired or Fired

### サブタイトル

AI Code Review Challenge

### 一文説明

AIが書いたコードをレビューできるか。5分のレビュー面接で、AI時代のエンジニア力を判定する。

### コンセプト

Hired or Fired は、AI時代のエンジニアに必要なコードレビュー力を、5分の面接ゲームとして鍛えるレビュー・トレーニングアプリである。

コードを書く力より先に、AIが出したコードを読み、疑い、要件とのズレを見抜く力を鍛える。

## 2. MVPスコープ

### 実装するもの

- Next.js + TypeScript + Tailwind CSS のWebアプリ
- トップ画面
- Interview Challenges 一覧
- Review Interview 画面
- Hiring Result 画面
- 行番号付きコード表示
- 行クリックによる選択
- 不具合カテゴリ、失敗パターン、正しい修正の階層選択
- 3段階ヒント
- スコア計算
- 5分タイマー
- 正解済みIssue行のチェック付きグレーアウト
- 発見ログ、誤指摘ログ
- カテゴリ別成績
- Hiring Rank 判定
- Review Rate 表示
- CSSベースのResult Illustration
- 正解音、不正解音、クリア音、ミュート設定
- LocalStorageによる問題別ベストスコア、ベストランク、プレイ回数保存
- スコア、ゲームエンジン、LocalStorage helper のテスト
- README

### 実装しないもの

- ネット対戦
- CPU対戦
- ログイン
- ユーザー管理
- ランキング
- データベース
- 自由コード編集
- Python実行環境
- AI採点
- サーバーサイド判定
- 課金機能
- モバイル完全最適化

## 3. 画面構成

### 3.1 トップ画面 `/`

目的は、プロダクトの世界観を一瞬で伝えること。

表示要素:

- H1: Hired or Fired
- サブコピー: AIが書いたコードを、あなたは見抜けるか？
- 説明文: AIがコードを書く時代、エンジニアに必要なのは生成する力だけではない。AIが出したコードを読み、疑い、要件とのズレを見抜く力である。
- 3ステップ説明
  - 要件を読む
  - 怪しい行を選ぶ
  - 不具合カテゴリ、失敗パターン、正しい修正を選ぶ
- CTA: レビュー面接を受ける
- CTA: Interview Challengesを見る

### 3.2 Interview Challenges `/problems`

問題一覧画面。問題カードは求人票風に見せる。

カード表示要素:

- Role
- Challenge title
- Difficulty
- 想定時間
- コード行数
- Issue数
- 主なカテゴリ
- Best Result
- Best Score

### 3.3 Review Interview `/play/[challengeId]`

デスクトップ3カラム構成。

左: Interview Brief

- 要件
- 入出力例
- 期待動作
- 制約
- 残り時間
- Review Score
- 発見済みIssue数 / 全Issue数
- 問題全体ヒント

中央: AI Generated Code

- 行番号付きコード
- 行クリック選択
- 行番号クリックでも選択可能
- 選択中の青ハイライト
- 解決済みIssueのチェック付きグレーアウト
- 未解決Issueの答えは見せない

右: Review Decision

- 選択中の行
- 選択行周辺コード
- 選択行ヒント
- Step 1: Issue Category / 不具合カテゴリ
- Step 2: Failure Pattern / 失敗パターン
- Step 3: Correct Fix / 正しい修正
- 正解直後の説明カード
- 発見ログ
- 直近の誤指摘ログ

### 3.4 Hiring Result `/result`

リザルト画面。

表示順:

1. Result Illustration
2. Hiring Rank
3. Review Score
4. Review Rate
5. Reviewer Type
6. カテゴリ別成績
7. 発見したIssue
8. 見逃したIssue
9. 誤指摘数
10. 使用ヒント
11. 次に鍛える観点
12. もう一度プレイ
13. Interview Challengesへ戻る

## 4. ゲームルール

- 1プレイは1問5分
- 問題を開いた時点ではタイマーを開始しない
- ユーザーが「レビュー開始」を押すとタイマー開始
- 開始前にも要件とコードは閲覧可能
- 行クリックだけでは減点しない
- 「この行を指摘する」または階層選択を確定した時点で判定する
- 選択行が未解決Issue範囲内なら、そのIssueの階層選択を進める
- バグではない行を指摘確定すると誤指摘として減点
- 正解すると該当行がチェック付きでグレーアウト
- 全Issue解決または時間切れで終了

## 5. スコア仕様

### 加点

- カテゴリ正解: +50
- 詳細タイプ正解: +75
- 修正コード正解: difficulty * 100
- 全Issue解決ボーナス: +300
- 全Issue解決時のみタイムボーナス: remainingSeconds * 2
- ノーミスボーナス: +200

### 減点

- カテゴリミス: -30
- 詳細タイプミス: -50
- 修正コードミス: -100
- 誤指摘: -50
- Hint 1: -20
- Hint 2: -50
- Hint 3: -100

## 6. Hiring Rank

最大スコアに対する割合で判定する。

```ts
scoreRate = finalScore / maxPossibleScore
```

| scoreRate | Hiring Rank |
| --- | --- |
| >= 0.9 | Strong Hire |
| >= 0.75 | Hire |
| >= 0.55 | Probation |
| >= 0.35 | No Hire |
| else | Fired |

Fired は最下位のみ。表示はコミカルかつ再挑戦を促す。

## 7. Review Rate

ゲーム内単価として表示する。

単位は `CR/h`。CR は Code Review Credit。

例:

```ts
if scoreRate >= 0.9: 12000 CR/h
if scoreRate >= 0.75: 8000 CR/h
if scoreRate >= 0.55: 5000 CR/h
if scoreRate >= 0.35: 2500 CR/h
else: 0 CR/h
```

## 8. Reviewer Type

カテゴリ別正答率が最も高いカテゴリから判定する。

MVPのReviewer Type:

- Logic Hunter
- Boundary Guard
- Flow Tracer
- Spec Reader
- Security Sentinel

同点の場合は固定優先順で判定する。

## 9. 初期問題

### Problem 1: 計算APIの演算子ミス

役割: ウォームアップ

狙い:

- 明確な演算子ミス
- 要件未充足
- ゲームルール理解

Issue例:

- add で乗算している
- subtract で除算している
- 未対応 operator でエラーではなく None を返す

### Problem 2: ユーザー登録判定の境界値・入力検証ミス

役割: 実務あるある

狙い:

- 境界値
- None / 不正入力
- 判定順序
- 要件の正確な読み取り

Issue例:

- 18歳ちょうどが登録不可になる
- age が None の場合に落ちる
- banned 判定の順序が遅い
- 負数年齢の考慮がない

### Problem 3: 注文割引・権限チェックの複合レビュー

役割: ボス問題

狙い:

- データフロー
- 要件ズレ
- セキュリティ / 権限
- 関数間契約

Issue例:

- 割引率が 0.2 ではなく 20 になっている
- discount を率ではなく金額として引いている
- 管理者チェックなしで手動割引できる
- 割引後価格がマイナスになる可能性がある

## 10. 型定義方針

主要型:

```ts
export type Difficulty = 1 | 2 | 3 | 4 | 5;

export type BugCategory =
  | "syntax"
  | "operator_mismatch"
  | "boundary"
  | "condition"
  | "data_flow"
  | "state_transition"
  | "security"
  | "requirement_mismatch"
  | "spec_ambiguity";

export type ReviewStepKind = "category" | "pattern" | "fix";

export type ReviewChoice = {
  id: string;
  label: string;
  description: string;
  isCorrect: boolean;
  explanation: string;
};

export type ReviewStep = {
  id: string;
  kind: ReviewStepKind;
  title: string;
  description: string;
  choices: ReviewChoice[];
};

export type Hint = {
  id: string;
  level: 1 | 2 | 3;
  text: string;
  penalty: number;
  revealType: "perspective" | "area" | "requirement_gap";
};

export type ReviewIssue = {
  id: string;
  title: string;
  description: string;
  startLine: number;
  endLine: number;
  difficulty: Difficulty;
  category: BugCategory;
  points: number;
  reviewSteps: ReviewStep[];
  hints: Hint[];
  successExplanation: string;
};

export type InterviewChallenge = {
  id: string;
  title: string;
  roleTitle: string;
  description: string;
  difficulty: Difficulty;
  estimatedMinutes: number;
  codeLineCount: number;
  requirements: string[];
  constraints: string[];
  expectedBehavior: string[];
  inputExamples: string[];
  code: string;
  challengeHints: Hint[];
  issues: ReviewIssue[];
};
```

## 11. 状態管理

MVPはReact state中心。

LocalStorageは以下に使う。

- 問題別ベストスコア
- ベストランク
- プレイ回数
- 最終リザルト
- 音ON/OFF設定

主要状態:

```ts
export type GameState = {
  challengeId: string;
  startedAt?: string;
  remainingSeconds: number;
  score: number;
  foundIssues: FoundIssue[];
  wrongAttempts: WrongAttempt[];
  usedHints: UsedHint[];
  currentSelection?: {
    selectedLine: number;
    issueId?: string;
    stepIndex: number;
    selectedChoiceIds: string[];
  };
  isCompleted: boolean;
};
```

## 12. 非機能要件

### 対応ブラウザ

- Chrome
- Edge

### 画面サイズ

- デスクトップ優先
- モバイルは縦積みで最低限崩れない

### 初回表示速度

- 3秒以内を目標

### オフライン利用

- 初回ロード後はクライアント完結で遊べる

### アクセシビリティ

- ボタンにラベルを付ける
- コード行はキーボードでも選択できる
- Enter / Space で選択可能にする
- 色だけに依存しない

### テスト

- スコア計算
- ゲームエンジン
- LocalStorage helpers
- 問題データ整合性

### セキュリティ

- 問題コードは文字列として表示する
- `dangerouslySetInnerHTML` を使わない
- 外部コードを実行しない
- Python実行環境を持たない

### デプロイ

- Vercel想定

### 最大コード行数

- MVPの想定最大コード行数は100行

## 13. 受け入れ条件

- `npm install` が成功する
- `npm run dev` が成功する
- トップ画面が表示される
- 問題一覧に3問表示される
- 問題を選んでReview Interviewに入れる
- レビュー開始ボタンで5分タイマーが始まる
- コード行をクリックできる
- Issue行で階層選択が進む
- カテゴリ、詳細、修正コードを選べる
- 正解するとスコアが増える
- 正解済み行がチェック付きでグレーアウトされる
- 不正解時に減点される
- 誤指摘時に減点される
- ヒントを使うと減点される
- 全Issue解決または時間切れで終了する
- Hiring Resultが表示される
- Result Illustrationが表示される
- Hiring Rank、Review Score、Review Rate、Reviewer Typeが表示される
- LocalStorageにベストスコアが保存される
- `npm test` が成功する
- `npm run build` が成功する

