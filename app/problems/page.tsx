import { ProblemsClient } from "@/components/ProblemsClient";

export default function ProblemsPage() {
  return (
    <main>
      <div className="section-header">
        <div>
          <p className="eyebrow">Interview Challenges</p>
          <h1 className="section-title">レビュー面接の求人票</h1>
          <p className="muted">
            AIが書いた「動きそうなコード」を、動かす前に疑えるか。
            求人票を選び、怪しい行、カテゴリ、失敗パターン、正しい修正まで言い切ってください。
          </p>
        </div>
      </div>

      <section className="problem-rule-panel" aria-label="共通の選考ルール">
        <div>
          <p className="eyebrow">Common interview rule</p>
          <h2>全求人共通の面接課題</h2>
          <p>
            仕様書とAI生成コードを照合し、怪しい行を指摘します。
            その後、カテゴリ、失敗パターン、正しい修正を順に選んで採用ラインを超えてください。
          </p>
        </div>
        <div className="problem-rule-steps">
          <span>1. 仕様を読む</span>
          <span>2. 怪しい行を選ぶ</span>
          <span>3. 修正まで言い切る</span>
        </div>
      </section>

      <ProblemsClient />
    </main>
  );
}
