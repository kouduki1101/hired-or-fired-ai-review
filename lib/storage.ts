import type { ChallengeRecord, GameResult } from "@/lib/types";

const LAST_RESULT_KEY = "hired_or_fired:last_result";
const RECORDS_KEY = "hired_or_fired:challenge_records";
const SOUND_KEY = "hired_or_fired:sound_enabled";

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function getBrowserStorage(): StorageLike | undefined {
  if (typeof window === "undefined") return undefined;
  return window.localStorage;
}

function safeParse<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function loadLastResult(storage = getBrowserStorage()) {
  return safeParse<GameResult | null>(storage?.getItem(LAST_RESULT_KEY) ?? null, null);
}

export function saveLastResult(
  result: GameResult,
  storage = getBrowserStorage()
) {
  storage?.setItem(LAST_RESULT_KEY, JSON.stringify(result));
}

export function loadChallengeRecords(storage = getBrowserStorage()) {
  return safeParse<Record<string, ChallengeRecord>>(
    storage?.getItem(RECORDS_KEY) ?? null,
    {}
  );
}

export function saveChallengeRecords(
  records: Record<string, ChallengeRecord>,
  storage = getBrowserStorage()
) {
  storage?.setItem(RECORDS_KEY, JSON.stringify(records));
}

export function updateChallengeRecord(
  result: GameResult,
  storage = getBrowserStorage()
) {
  const records = loadChallengeRecords(storage);
  const previous = records[result.challengeId];
  const bestScore = Math.max(previous?.bestScore ?? 0, result.finalScore);
  const bestRank =
    !previous || result.finalScore >= previous.bestScore
      ? result.rank
      : previous.bestRank;

  records[result.challengeId] = {
    challengeId: result.challengeId,
    bestScore,
    bestRank,
    playCount: (previous?.playCount ?? 0) + 1,
    lastResult: result
  };

  saveChallengeRecords(records, storage);
  return records[result.challengeId];
}

export function loadSoundEnabled(storage = getBrowserStorage()) {
  return safeParse<boolean>(storage?.getItem(SOUND_KEY) ?? null, true);
}

export function saveSoundEnabled(enabled: boolean, storage = getBrowserStorage()) {
  storage?.setItem(SOUND_KEY, JSON.stringify(enabled));
}

export function clearLocalProgress(storage = getBrowserStorage()) {
  storage?.removeItem(LAST_RESULT_KEY);
  storage?.removeItem(RECORDS_KEY);
}
