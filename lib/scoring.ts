import type {
  CategoryStats,
  HiringRank,
  InterviewChallenge,
  ReviewCategory,
  ReviewerType,
  ReviewStepKind
} from "@/lib/types";

export const SCORE = {
  categoryCorrect: 50,
  patternCorrect: 75,
  completionBonus: 300,
  noMissBonus: 200,
  timeBonusPerSecond: 2,
  wrongCategory: -30,
  wrongPattern: -50,
  wrongFix: -100,
  wrongLine: -50,
  hint: [-20, -50, -100]
} as const;

const categoryToReviewerType: Record<ReviewCategory, ReviewerType> = {
  spec: "Spec Reader",
  logic: "Logic Hunter",
  boundary: "Boundary Guard",
  data_flow: "Flow Tracer",
  security: "Security Sentinel"
};

const reviewerPriority: ReviewCategory[] = [
  "logic",
  "boundary",
  "data_flow",
  "spec",
  "security"
];

export function getCorrectStepScore(
  kind: ReviewStepKind,
  difficulty: number
): number {
  if (kind === "category") return SCORE.categoryCorrect;
  if (kind === "pattern") return SCORE.patternCorrect;
  return difficulty * 100;
}

export function getWrongStepPenalty(kind: ReviewStepKind): number {
  if (kind === "category") return SCORE.wrongCategory;
  if (kind === "pattern") return SCORE.wrongPattern;
  return SCORE.wrongFix;
}

export function getHintPenalty(hintIndex: number): number {
  return SCORE.hint[Math.min(hintIndex, SCORE.hint.length - 1)];
}

export function getMaxPossibleScore(challenge: InterviewChallenge): number {
  const issueScore = challenge.issues.reduce((total, issue) => {
    return (
      total +
      SCORE.categoryCorrect +
      SCORE.patternCorrect +
      issue.difficulty * 100
    );
  }, 0);

  return (
    issueScore +
    SCORE.completionBonus +
    SCORE.noMissBonus +
    challenge.timeLimitSeconds * SCORE.timeBonusPerSecond
  );
}

export function getHiringRank(score: number, maxScore: number): HiringRank {
  const rate = maxScore <= 0 ? 0 : score / maxScore;
  if (rate >= 0.9) return "Strong Hire";
  if (rate >= 0.75) return "Hire";
  if (rate >= 0.55) return "Probation";
  if (rate >= 0.35) return "No Hire";
  return "Fired";
}

export function getReviewRate(rank: HiringRank): number {
  if (rank === "Strong Hire") return 12000;
  if (rank === "Hire") return 8000;
  if (rank === "Probation") return 5000;
  if (rank === "No Hire") return 2500;
  return 0;
}

export function createEmptyCategoryStats(): CategoryStats {
  return {
    spec: { correct: 0, attempts: 0 },
    logic: { correct: 0, attempts: 0 },
    boundary: { correct: 0, attempts: 0 },
    data_flow: { correct: 0, attempts: 0 },
    security: { correct: 0, attempts: 0 }
  };
}

export function getReviewerType(stats: CategoryStats): ReviewerType {
  let bestCategory: ReviewCategory = reviewerPriority[0];
  let bestRate = -1;
  let bestCorrect = -1;

  for (const category of reviewerPriority) {
    const item = stats[category];
    const rate = item.attempts === 0 ? 0 : item.correct / item.attempts;
    if (rate > bestRate || (rate === bestRate && item.correct > bestCorrect)) {
      bestCategory = category;
      bestRate = rate;
      bestCorrect = item.correct;
    }
  }

  return categoryToReviewerType[bestCategory];
}

export function clampScore(score: number): number {
  return Math.max(0, score);
}
