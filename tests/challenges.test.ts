import { describe, expect, it } from "vitest";
import { challenges } from "@/data/challenges";
import { getCodeLines } from "@/lib/gameEngine";

describe("challenge data integrity", () => {
  it("keeps the public interview list curated", () => {
    expect(challenges.length).toBeGreaterThanOrEqual(35);
    expect(challenges.length).toBeLessThanOrEqual(60);
  });

  it("does not expose domain-cloned generated challenges as separate postings", () => {
    const generatedVisible = challenges.filter((challenge) =>
      /^(supply|billing|hr|learning)-/.test(challenge.id)
    );
    const patternKeys = generatedVisible.map((challenge) =>
      challenge.id.replace(/^(supply|billing|hr|learning)-/, "").replace(/-review$/, "")
    );

    expect(new Set(patternKeys).size).toBe(patternKeys.length);
  });

  it("has unique challenge ids", () => {
    const ids = challenges.map((challenge) => challenge.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("does not expose mechanically glued generated Japanese titles", () => {
    for (const challenge of challenges) {
      expect(challenge.title).not.toMatch(/^(調達|請求|人事|学習)の/);
      expect(challenge.title).not.toContain("早すぎるreturn");
    }
  });

  it("keeps code within the MVP maximum of 100 lines", () => {
    for (const challenge of challenges) {
      expect(getCodeLines(challenge.code).length).toBeLessThanOrEqual(100);
    }
  });

  it("keeps issue ranges inside code lines", () => {
    for (const challenge of challenges) {
      const lineCount = getCodeLines(challenge.code).length;
      for (const issue of challenge.issues) {
        expect(issue.startLine).toBeGreaterThanOrEqual(1);
        expect(issue.endLine).toBeGreaterThanOrEqual(issue.startLine);
        expect(issue.endLine).toBeLessThanOrEqual(lineCount);
      }
    }
  });

  it("has exactly one correct choice per review step", () => {
    for (const challenge of challenges) {
      for (const issue of challenge.issues) {
        expect(issue.hints.length).toBeGreaterThanOrEqual(3);
        expect(issue.steps.map((step) => step.kind)).toEqual([
          "category",
          "pattern",
          "fix"
        ]);
        for (const step of issue.steps) {
          expect(step.choices.filter((choice) => choice.correct)).toHaveLength(1);
        }
      }
    }
  });
});
