import { describe, expect, it } from "vitest";
import {
  loadChallengeRecords,
  loadLastResult,
  loadSoundEnabled,
  saveLastResult,
  saveSoundEnabled,
  updateChallengeRecord
} from "@/lib/storage";
import type { GameResult } from "@/lib/types";

function createMemoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key)
  };
}

const baseResult: GameResult = {
  challengeId: "calc-api-operator-review",
  finalScore: 1000,
  maxScore: 1200,
  scoreRate: 0.83,
  rank: "Hire",
  reviewRate: 8000,
  reviewerType: "Logic Hunter",
  foundIssueIds: ["a"],
  missedIssueIds: [],
  wrongAttempts: [],
  hintsUsed: 0,
  elapsedSeconds: 120,
  categoryStats: {
    spec: { correct: 0, attempts: 0 },
    logic: { correct: 3, attempts: 3 },
    boundary: { correct: 0, attempts: 0 },
    data_flow: { correct: 0, attempts: 0 },
    security: { correct: 0, attempts: 0 }
  },
  finishedAt: "2026-06-04T00:00:00.000Z"
};

describe("storage helpers", () => {
  it("saves and loads the last result", () => {
    const storage = createMemoryStorage();
    saveLastResult(baseResult, storage);
    expect(loadLastResult(storage)?.rank).toBe("Hire");
  });

  it("updates challenge records with best score and play count", () => {
    const storage = createMemoryStorage();
    updateChallengeRecord(baseResult, storage);
    updateChallengeRecord({ ...baseResult, finalScore: 500, rank: "No Hire" }, storage);
    const records = loadChallengeRecords(storage);
    expect(records[baseResult.challengeId].bestScore).toBe(1000);
    expect(records[baseResult.challengeId].bestRank).toBe("Hire");
    expect(records[baseResult.challengeId].playCount).toBe(2);
  });

  it("persists sound setting", () => {
    const storage = createMemoryStorage();
    expect(loadSoundEnabled(storage)).toBe(true);
    saveSoundEnabled(false, storage);
    expect(loadSoundEnabled(storage)).toBe(false);
  });
});
