import type { HiringRank } from "@/lib/types";

type Props = {
  rank: HiringRank;
};

function getMood(rank: HiringRank) {
  if (rank === "Strong Hire" || rank === "Hire") return "hired";
  if (rank === "Probation") return "middle";
  return "fired";
}

function getBadge(rank: HiringRank) {
  if (rank === "Strong Hire") return "SIGNED";
  if (rank === "Hire") return "OFFER";
  if (rank === "Probation") return "CALLBACK";
  if (rank === "No Hire") return "NO HIRE";
  return "FIRED";
}

function getSceneCopy(rank: HiringRank) {
  if (rank === "Strong Hire") return "Review board approved";
  if (rank === "Hire") return "Offer packet unlocked";
  if (rank === "Probation") return "One more round requested";
  if (rank === "No Hire") return "Review gaps detected";
  return "Training run failed";
}

export function ResultIllustration({ rank }: Props) {
  const mood = getMood(rank);
  const badge = getBadge(rank);
  const sceneCopy = getSceneCopy(rank);

  return (
    <div
      className={`result-illustration ${mood}`}
      aria-label={`Result illustration: ${rank}`}
    >
      <div className="arena-grid" />
      <div className="stage-lights">
        <span />
        <span />
        <span />
      </div>
      <div className="verdict-board">
        <span className="board-kicker">HIRING RESULT</span>
        <strong>{badge}</strong>
        <span>{sceneCopy}</span>
      </div>
      <div className="score-terminal">
        <span>review.exe</span>
        <b>{rank}</b>
        <small>skills scanned</small>
      </div>
      <div className="interview-desk">
        <span className="desk-leg left" />
        <span className="desk-leg right" />
      </div>
      <div className="illustration-person">
        <div className="illustration-head">
          <span className="hair" />
        </div>
        <div className="illustration-body">
          <span className="tie" />
        </div>
      </div>
      <div className="result-ticket">
        <span>{mood === "hired" ? "CONTRACT" : mood === "middle" ? "REVIEW" : "RETRY"}</span>
      </div>
      <span className="spark spark-a" />
      <span className="spark spark-b" />
      <span className="spark spark-c" />
    </div>
  );
}
