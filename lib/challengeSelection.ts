import type { ChallengeRecord } from "@/lib/types";

export function pickNextChallengeId(
  challengeIds: string[],
  records: Record<string, ChallengeRecord>,
  options: {
    excludeChallengeId?: string;
    random?: () => number;
  } = {}
) {
  const random = options.random ?? Math.random;
  if (challengeIds.length === 0) return undefined;

  const candidates = challengeIds.filter(
    (id) => id !== options.excludeChallengeId
  );
  const pool = candidates.length > 0 ? candidates : challengeIds;

  const unplayed = pool.filter((id) => !records[id]);
  if (unplayed.length > 0) {
    return pickRandom(unplayed, random);
  }

  const minPlayCount = Math.min(
    ...pool.map((id) => records[id]?.playCount ?? 0)
  );
  const leastPlayed = pool.filter(
    (id) => (records[id]?.playCount ?? 0) === minPlayCount
  );

  return pickRandom(leastPlayed, random);
}

function pickRandom(items: string[], random: () => number) {
  const index = Math.min(items.length - 1, Math.floor(random() * items.length));
  return items[index];
}
