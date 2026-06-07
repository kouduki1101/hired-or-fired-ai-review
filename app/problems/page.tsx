import { ProblemsClient } from "@/components/ProblemsClient";

export default function ProblemsPage() {
  return (
    <main>
      <div className="section-header">
        <div>
          <p className="eyebrow">Interview Challenges</p>
          <h1 className="section-title">レビュー面接の求人票</h1>
          <p className="muted">
            募集要項はただ一つ。AIが書いた「動きそうなコード」を、動かす前に見抜けること。
            5分の選考コードで、Hiredを取りにいく。
          </p>
        </div>
      </div>

      <ProblemsClient />
    </main>
  );
}
