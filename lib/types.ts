export type ReviewCategory =
  | "spec"
  | "logic"
  | "boundary"
  | "data_flow"
  | "security";

export type HiringRank =
  | "Strong Hire"
  | "Hire"
  | "Probation"
  | "No Hire"
  | "Fired";

export type ReviewerType =
  | "Spec Reader"
  | "Logic Hunter"
  | "Boundary Guard"
  | "Flow Tracer"
  | "Security Sentinel";

export type ReviewStepKind = "category" | "pattern" | "fix";

export type ReviewChoice = {
  id: string;
  label: string;
  description: string;
  code?: string;
  correct: boolean;
};

export type ReviewStep = {
  kind: ReviewStepKind;
  prompt: string;
  choices: ReviewChoice[];
};

export type ReviewIssue = {
  id: string;
  title: string;
  category: ReviewCategory;
  pattern: string;
  startLine: number;
  endLine: number;
  difficulty: 1 | 2 | 3 | 4 | 5;
  summary: string;
  explanation: string;
  correctCode: string;
  hints: string[];
  steps: ReviewStep[];
};

export type InterviewChallenge = {
  id: string;
  role: string;
  title: string;
  difficultyLabel: string;
  estimatedMinutes: number;
  timeLimitSeconds: number;
  codeLanguage: "python";
  requirements: string[];
  examples: string[];
  constraints: string[];
  code: string;
  issues: ReviewIssue[];
  challengeHints: string[];
};

export type WrongAttemptReason =
  | "not_an_issue"
  | "wrong_category"
  | "wrong_pattern"
  | "wrong_fix";

export type WrongAttempt = {
  issueId?: string;
  line?: number;
  reason: WrongAttemptReason;
  message: string;
};

export type FoundIssue = {
  issueId: string;
  foundAtSeconds: number;
  scoreDelta: number;
};

export type CategoryStats = Record<
  ReviewCategory,
  {
    correct: number;
    attempts: number;
  }
>;

export type GameResult = {
  challengeId: string;
  finalScore: number;
  maxScore: number;
  scoreRate: number;
  rank: HiringRank;
  reviewRate: number;
  reviewerType: ReviewerType;
  foundIssueIds: string[];
  missedIssueIds: string[];
  wrongAttempts: WrongAttempt[];
  hintsUsed: number;
  elapsedSeconds: number;
  categoryStats: CategoryStats;
  finishedAt: string;
};

export type ChallengeRecord = {
  challengeId: string;
  bestScore: number;
  bestRank: HiringRank;
  playCount: number;
  lastResult?: GameResult;
};
