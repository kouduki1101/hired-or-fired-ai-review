"use client";

import { useEffect, useState } from "react";
import { ChallengeCard } from "@/components/ChallengeCard";
import { challenges } from "@/data/challenges";
import { loadChallengeRecords } from "@/lib/storage";
import type { ChallengeRecord } from "@/lib/types";

export function ProblemsClient() {
  const [records, setRecords] = useState<Record<string, ChallengeRecord>>({});

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setRecords(loadChallengeRecords());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="challenge-grid">
      {challenges.map((challenge) => (
        <ChallengeCard
          key={challenge.id}
          challenge={challenge}
          record={records[challenge.id]}
        />
      ))}
    </div>
  );
}
