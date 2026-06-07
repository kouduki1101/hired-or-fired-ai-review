# Hired or Fired

AI Code Review Challenge.

AIが書いたコードを人間がレビューし、要件とのズレを見抜く5分のレビュー面接ゲームです。コードを書く力より先に、生成コードを読み、疑い、正しい修正まで言い切る力を鍛えることを目的にしています。

## MVP Scope

- トップ画面
- Python Review Guide 解説ページ
- Interview Challenges 一覧
- Review Interview 画面
- Hiring Result 画面
- Pythonコードレビュー問題10問
- 行クリックによるIssue選択
- Issue Category / Failure Pattern / Correct Fix の階層選択
- 3段階Hint
- スコア、Hiring Rank、Review Rate、Reviewer Type
- 正解Issueのグレーアウト
- 正解、ミス、クリア音
- LocalStorageによるベストスコア保存
- 採点、ゲームエンジン、データ整合性テスト
- 未プレイ優先のランダム問題開始

## Learning Loop

1. `/learn/python` でPythonレビューの基礎知識を読む
2. `/problems` で対応する問題を選ぶ
3. `/play/[challengeId]` でAI生成コードをレビューする
4. `/result` で弱点カテゴリを見る
5. 弱点に対応する章へ戻る

## Commands

```bash
npm install
npm run dev
npm test
npx tsc --noEmit
```

Local URL:

```txt
http://localhost:3000
```

## Notes

ローカル環境ではNext.js 15の`npm run build`がOneDrive配下で長時間停止することがあります。MVPの実装検証は`npm test`と`npx tsc --noEmit`、および`npm run dev`での画面確認で実施しています。

本番ビルドを安定化する場合は、次のいずれかを推奨します。

- OneDrive外の短いパスに作業フォルダを移す
- Next.jsのバージョンを固定して再検証する
- 静的ゲームとしてVite構成に切り替える

## Non-goals

- ログイン
- DB
- ネット対戦
- CPU対戦
- Pythonコード実行
- AI採点
- 自由記述コード修正
