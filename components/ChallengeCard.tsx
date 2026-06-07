import Link from "next/link";
import { categoryLabels } from "@/data/challenges";
import type { ChallengeRecord, InterviewChallenge } from "@/lib/types";

type Props = {
  challenge: InterviewChallenge;
  record?: ChallengeRecord;
};

export function ChallengeCard({ challenge, record }: Props) {
  const categories = Array.from(
    new Set(challenge.issues.map((issue) => categoryLabels[issue.category]))
  );
  const issueCount = challenge.issues.length;
  const lineCount = challenge.code.split("\n").length;

  return (
    <article className="challenge-card">
      <div className="job-posting-head">
        <div className="job-meta">
          <span className="pill">募集職種</span>
          <span className="pill">{challenge.role}</span>
        </div>
        <h2>
          {challenge.title}
        </h2>
        <p className="job-copy">
          求む。AIが書いたもっともらしいPythonを、実行前に疑えるレビュアー。
        </p>
        <p className="panel-muted">
          選考時間: {challenge.estimatedMinutes}分 / 難易度: {challenge.difficultyLabel}
        </p>
      </div>

      <div className="job-meta">
        <span className="pill">不具合候補 {issueCount}件</span>
        <span className="pill">{lineCount}行の選考コード</span>
      </div>

      <div className="job-requirement">
        <strong>この求人で見るレビュー筋</strong>
        <div className="job-meta" style={{ marginTop: 10 }}>
          {categories.map((category) => (
            <span className="pill" key={category}>
              {category}
            </span>
          ))}
        </div>
      </div>

      <div className="job-brief">
        <strong>面接課題</strong>
        <p>
          仕様書とAI生成コードを照合し、怪しい行を指摘。カテゴリ、失敗パターン、
          正しい修正を順に選んで、採用ラインを超えてください。
        </p>
      </div>

      <div className="card-footer">
        <div className="metric-grid">
          <div className="metric light">
            <span className="panel-muted">Best</span>
            <b>{record?.bestRank ?? "No run"}</b>
          </div>
          <div className="metric light">
            <span className="panel-muted">Score</span>
            <b>{record?.bestScore ?? 0}</b>
          </div>
        </div>
        {record && (
          <p className="panel-muted" style={{ margin: 0 }}>
            Played {record.playCount} time{record.playCount === 1 ? "" : "s"}.
            前回の結果を超えにいく。
          </p>
        )}
        <Link className="primary-button" href={`/play/${challenge.id}`}>
          {record ? "この求人に再応募する" : "この求人に応募する"}
        </Link>
      </div>
    </article>
  );
}
