import { describe, expect, it } from "vitest";
import { pickNextChallengeId } from "@/lib/challengeSelection";
import type { ChallengeRecord } from "@/lib/types";

const ids = ["a", "b", "c"];

function record(id: string, playCount: number): ChallengeRecord {
  return {
    challengeId: id,
    bestScore: 0,
    bestRank: "Fired",
    playCount
  };
}

describe("challenge selection", () => {
  it("picks from unplayed challenges first", () => {
    const records = { a: record("a", 1) };
    expect(pickNextChallengeId(ids, records, { random: () => 0 })).toBe("b");
    expect(pickNextChallengeId(ids, records, { random: () => 0.99 })).toBe("c");
  });

  it("avoids the current challenge when possible", () => {
    const records = {
      a: record("a", 1),
      b: record("b", 1),
      c: record("c", 1)
    };
    expect(
      pickNextChallengeId(ids, records, {
        excludeChallengeId: "a",
        random: () => 0
      })
    ).toBe("b");
  });

  it("falls back to least played challenges after all are played", () => {
    const records = {
      a: record("a", 3),
      b: record("b", 1),
      c: record("c", 2)
    };
    expect(pickNextChallengeId(ids, records, { random: () => 0.5 })).toBe("b");
  });
});
