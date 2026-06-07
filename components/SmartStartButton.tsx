"use client";

import { useRouter } from "next/navigation";
import { challenges } from "@/data/challenges";
import { pickNextChallengeId } from "@/lib/challengeSelection";
import { loadChallengeRecords } from "@/lib/storage";

type Props = {
  className?: string;
  children: React.ReactNode;
  excludeChallengeId?: string;
};

export function SmartStartButton({
  className = "primary-button",
  children,
  excludeChallengeId
}: Props) {
  const router = useRouter();

  function start() {
    const records = loadChallengeRecords();
    const nextId = pickNextChallengeId(
      challenges.map((challenge) => challenge.id),
      records,
      { excludeChallengeId }
    );
    router.push(nextId ? `/play/${nextId}` : "/problems");
  }

  return (
    <button className={className} type="button" onClick={start}>
      {children}
    </button>
  );
}
