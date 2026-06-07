import Link from "next/link";
import { challenges } from "@/data/challenges";
import { SmartStartButton } from "@/components/SmartStartButton";

export default function HomePage() {
  const issueCount = challenges.reduce(
    (total, challenge) => total + challenge.issues.length,
    0
  );

  return (
    <main>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">AI code review interview</p>
          <h1>Hired or Fired</h1>
          <p className="hero-subtitle">
            AI面接官に、レビュー筋を見せつけろ。
          </p>
          <p className="hero-description">
            AIが出したコードレビュー課題に挑み、怪しい行、カテゴリ、失敗パターン、
            正しい修正を順に見抜く。高スコアなら Hired。見落とせば Fired。
          </p>
          <div className="hero-actions">
            <SmartStartButton>
              レビュー面接を受ける
            </SmartStartButton>
            <Link className="soft-button" href="/problems">
              求人票を見る
            </Link>
            <Link className="soft-button" href="/learn/python">
              レビュー型帳で予習する
            </Link>
          </div>
        </div>

        <aside className="interview-card" aria-label="How to play">
          <div className="hero-verdict-illustration" aria-hidden="true">
            <div className="ai-interviewer-badge">AI INTERVIEWER</div>
            <div className="verdict-stamp hired">HIRED</div>
            <div className="verdict-stamp fired">FIRED</div>
            <div className="mini-code-paper">
              <span />
              <span />
              <span />
              <b>if not value:</b>
            </div>
            <div className="reviewer-avatar">
              <div className="reviewer-head" />
              <div className="reviewer-body" />
            </div>
            <div className="verdict-desk" />
          </div>
          <span className="pill">New training concept</span>
          <h2 className="section-title" style={{ marginTop: 16 }}>
            書く前に、見抜け。
          </h2>
          <div className="steps">
            <div className="step-item">
              <span className="step-number">1</span>
              <div>
                <strong>要件を読む</strong>
                <p className="panel-muted">
                  入出力例、制約、境界値を先に頭へ入れる。
                </p>
              </div>
            </div>
            <div className="step-item">
              <span className="step-number">2</span>
              <div>
                <strong>怪しい行を選ぶ</strong>
                <p className="panel-muted">
                  行クリックだけでは減点なし。指摘確定で判定されます。
                </p>
              </div>
            </div>
            <div className="step-item">
              <span className="step-number">3</span>
              <div>
                <strong>修正まで言い切る</strong>
                <p className="panel-muted">
                  カテゴリ、失敗パターン、正しい修正を階層選択します。
                </p>
              </div>
            </div>
          </div>
          <div className="verdict-rule">
            <span>Hired: 修正まで言い切る</span>
            <span>Fired: 怪しいだけで止まる</span>
          </div>
        </aside>
      </section>

      <section className="section">
        <div className="section-header">
          <div>
            <h2>Open Review Positions</h2>
            <p className="muted">
              {challenges.length} challenges / {issueCount} hidden issues / 5 minutes each / unplayed-first random
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
