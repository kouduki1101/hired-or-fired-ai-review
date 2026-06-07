import { describe, expect, it } from "vitest";
import { challenges } from "@/data/challenges";
import {
  SCORE,
  createEmptyCategoryStats,
  getCorrectStepScore,
  getHiringRank,
  getMaxPossibleScore,
  getReviewRate,
  getReviewerType,
  getWrongStepPenalty
} from "@/lib/scoring";

describe("scoring", () => {
  it("scores each review step deterministically", () => {
    expect(getCorrectStepScore("category", 3)).toBe(SCORE.categoryCorrect);
    expect(getCorrectStepScore("pattern", 3)).toBe(SCORE.patternCorrect);
    expect(getCorrectStepScore("fix", 3)).toBe(300);
    expect(getWrongStepPenalty("fix")).toBe(SCORE.wrongFix);
  });

  it("calculates max possible score from issue difficulty and timer", () => {
    const challenge = challenges[0];
    const expectedIssueScore = challenge.issues.reduce(
      (total, issue) => total + 50 + 75 + issue.difficulty * 100,
      0
    );
    expect(getMaxPossibleScore(challenge)).toBe(
      expectedIssueScore + 300 + 200 + 300 * 2
    );
  });

  it("maps score rate to hiring rank and review rate", () => {
    expect(getHiringRank(90, 100)).toBe("Strong Hire");
    expect(getHiringRank(76, 100)).toBe("Hire");
    expect(getHiringRank(56, 100)).toBe("Probation");
    expect(getHiringRank(36, 100)).toBe("No Hire");
    expect(getHiringRank(10, 100)).toBe("Fired");
    expect(getReviewRate("Hire")).toBe(8000);
  });

  it("chooses reviewer type from best category performance", () => {
    const stats = createEmptyCategoryStats();
    stats.security.attempts = 3;
    stats.security.correct = 3;
    stats.logic.attempts = 2;
    stats.logic.correct = 1;
    expect(getReviewerType(stats)).toBe("Security Sentinel");
  });
});
