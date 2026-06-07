"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ResultIllustration } from "@/components/ResultIllustration";
import { SmartStartButton } from "@/components/SmartStartButton";
import { categoryLabels, getChallengeById } from "@/data/challenges";
import { loadLastResult } from "@/lib/storage";
import type { GameResult, ReviewCategory } from "@/lib/types";

const categoryOrder: ReviewCategory[] = [
  "logic",
  "boundary",
  "data_flow",
  "spec",
  "security"
];

function getRankCopy(rank: GameResult["rank"]) {
  if (rank === "Strong Hire") {
    return "AI時代のレビュー面接なら即オファー。要件とコードの差分をかなり高い精度で見抜けています。";
  }
  if (rank === "Hire") {
    return "採用ラインです。見落としを少し減らせば、さらに高単価レビューに届きます。";
  }
  if (rank === "Probation") {
    return "伸びしろあり。レビューの筋はありますが、境界値や権限条件の詰めがまだ甘いです。";
  }
  if (rank === "No Hire") {
    return "今回は見送り。ただ、どこで外したかが見えています。次はカテゴリ選択をゆっくり固めよう。";
  }
  return "Fired。ただしこれは練習面接です。次はHintを使ってもいいので、要件と行の対応から鍛え直そう。";
}

export function ResultClient() {
  const [result, setResult] = useState<GameResult | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setResult(loadLastResult());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const challenge = useMemo(() => {
    return result ? getChallengeById(result.challengeId) : undefined;
  }, [result]);

  if (!result || !challenge) {
    return (
      <main className="light-card">
        <h1 style={{ marginTop: 0 }}>No interview result</h1>
        <p className="panel-muted">
          まだレビュー面接の結果がありません。まずはChallengeを1つ受けてください。
        </p>
        <Link className="primary-button" href="/problems">
          Interview Challengesへ
        </Link>
      </main>
    );
  }

  const foundIssues = challenge.issues.filter((issue) =>
    result.foundIssueIds.includes(issue.id)
  );
  const missedIssues = challenge.issues.filter((issue) =>
    result.missedIssueIds.includes(issue.id)
  );

  return (
    <main>
      <div className="section-header">
        <div>
          <p className="eyebrow">Hiring Result</p>
          <h1 className="section-title">{challenge.title}</h1>
          <p className="muted">{getRankCopy(result.rank)}</p>
        </div>
        <div className="nav-links">
          <Link className="nav-link" href="/problems">
            Interview Challenges
          </Link>
          <Link className="soft-button" href={`/play/${challenge.id}`}>
            同じ面接を再挑戦
          </Link>
          <SmartStartButton excludeChallengeId={challenge.id}>
            次の面接へ
          </SmartStartButton>
        </div>
      </div>

      <div className="result-layout">
        <section className="light-card">
          <ResultIllustration rank={result.rank} />
          <h2 className="rank-title" style={{ marginTop: 18 }}>
            {result.rank}
          </h2>
          <p className="panel-muted">Reviewer Type: {result.reviewerType}</p>
          <div className="metric-grid" style={{ marginTop: 16 }}>
            <div className="metric light">
              <span className="panel-muted">Review Score</span>
              <b>
                {result.finalScore}/{result.maxScore}
              </b>
            </div>
            <div className="metric light">
              <span className="panel-muted">Review Rate</span>
              <b>{result.reviewRate.toLocaleString()} CR/h</b>
            </div>
            <div className="metric light">
              <span className="panel-muted">Found</span>
              <b>
                {result.foundIssueIds.length}/{challenge.issues.length}
              </b>
            </div>
            <div className="metric light">
              <span className="panel-muted">Miss / Hint</span>
              <b>
                {result.wrongAttempts.length} / {result.hintsUsed}
              </b>
            </div>
          </div>
        </section>

        <section className="dark-card">
          <h2 style={{ marginTop: 0 }}>Category Performance</h2>
          <div className="category-bars">
            {categoryOrder.map((category) => {
              const stat = result.categoryStats[category];
              const rate = stat.attempts === 0 ? 0 : stat.correct / stat.attempts;
              return (
                <div className="bar-row" key={category}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12
                    }}
                  >
                    <span>{categoryLabels[category]}</span>
                    <span className="muted">
                      {stat.correct}/{stat.attempts}
                    </span>
                  </div>
                  <div className="bar-track">
                    <div
                      className="bar-fill"
                      style={{ width: `${Math.round(rate * 100)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <h3>Found Issues</h3>
          <div className="log-list">
            {foundIssues.map((issue) => (
              <div className="log-item" key={issue.id}>
                <strong>{issue.title}</strong>
                <br />
                <span className="muted">{issue.explanation}</span>
              </div>
            ))}
            {foundIssues.length === 0 && (
              <div className="log-item">解決済みIssueはありません。</div>
            )}
          </div>

          <h3>Missed Issues</h3>
          <div className="log-list">
            {missedIssues.map((issue) => (
              <div className="log-item" key={issue.id}>
                <strong>{issue.title}</strong>
                <br />
                <span className="muted">
                  次回は {issue.startLine} 行目付近の {categoryLabels[issue.category]} を確認。
                </span>
              </div>
            ))}
            {missedIssues.length === 0 && (
              <div className="log-item">見落としなし。かなり良いレビューです。</div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
