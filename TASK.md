# TASK.md

# Hired or Fired MVP 実装タスク

## 目的

AIコードレビュー面接ゲーム Hired or Fired のMVPを実装する。

## 実装スタック

- Next.js
- TypeScript
- Tailwind CSS
- Vitest
- React state
- LocalStorage

## 実装する画面

- `/`: トップ画面
- `/problems`: Interview Challenges
- `/play/[challengeId]`: Review Interview
- `/result`: Hiring Result

## 実装する主要機能

- 3問のInterview Challenge
- 行番号付きコード表示
- 行クリック選択
- Issue Category / Failure Pattern / Correct Fix の階層選択
- 3段階ヒント
- スコア計算
- 5分タイマー
- 正解済み行のチェック付きグレーアウト
- 発見ログ
- 誤指摘ログ
- Hiring Rank
- Review Rate
- Reviewer Type
- CSSベースResult Illustration
- 正解音、不正解音、クリア音、ミュート設定
- LocalStorage保存

## 推奨ファイル構成

```txt
app/
  page.tsx
  problems/
    page.tsx
  play/
    [challengeId]/
      page.tsx
  result/
    page.tsx

components/
  ChallengeCard.tsx
  CodeViewer.tsx
  InterviewBrief.tsx
  GameStatusPanel.tsx
  ReviewDecisionPanel.tsx
  FoundIssueLog.tsx
  ResultSummary.tsx
  ResultIllustration.tsx
  SoundToggle.tsx

data/
  challenges.ts

lib/
  types.ts
  gameEngine.ts
  scoring.ts
  storage.ts
  sound.ts

tests/
  scoring.test.ts
  gameEngine.test.ts
  storage.test.ts
  challenges.test.ts

README.md
```

## 実装順序

1. Next.js / TypeScript / Tailwind / Vitest セットアップ
2. 型定義
3. スコア・ランク計算
4. ゲームエンジン
5. 問題データ3問
6. LocalStorage helpers
7. トップ画面
8. 問題一覧画面
9. Review Interview画面
10. Hiring Result画面
11. 音・演出
12. テスト
13. README

## 完了条件

- 3問をプレイできる
- 5分タイマーが動く
- 階層選択でレビュー判断できる
- 正解・不正解・誤指摘・ヒント使用でスコアが変わる
- 正解済み行がグレーアウトする
- Hiring Resultが出る
- Result Illustrationが出る
- LocalStorageにベストスコアが残る
- `npm test` が成功する
- `npm run build` が成功する

