import { describe, expect, it } from "vitest";
import { challenges } from "@/data/challenges";
import {
  areAllIssuesResolved,
  getCodeLines,
  getIssueForLine,
  isCorrectChoice
} from "@/lib/gameEngine";

describe("game engine", () => {
  const challenge = challenges[0];

  it("splits code into numbered lines", () => {
    expect(getCodeLines(challenge.code)[0]).toContain("def calculate_total");
  });

  it("detects an unresolved issue by selected line", () => {
    expect(getIssueForLine(challenge, 3)?.id).toBe("calc-add-multiplies");
  });

  it("does not return resolved issues", () => {
    expect(getIssueForLine(challenge, 3, ["calc-add-multiplies"])).toBeUndefined();
  });

  it("validates hierarchical choices", () => {
    const issue = challenge.issues[0];
    expect(isCorrectChoice(issue, "category", "logic")).toBe(true);
    expect(isCorrectChoice(issue, "category", "spec")).toBe(false);
  });

  it("detects completion only when every issue is resolved", () => {
    expect(areAllIssuesResolved(challenge, [])).toBe(false);
    expect(
      areAllIssuesResolved(
        challenge,
        challenge.issues.map((issue) => issue.id)
      )
    ).toBe(true);
  });
});
