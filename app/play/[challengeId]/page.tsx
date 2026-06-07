import { notFound } from "next/navigation";
import { PlayClient } from "@/components/PlayClient";
import { challenges, getChallengeById } from "@/data/challenges";

export function generateStaticParams() {
  return challenges.map((challenge) => ({
    challengeId: challenge.id
  }));
}

export default async function PlayPage({
  params
}: {
  params: Promise<{ challengeId: string }>;
}) {
  const { challengeId } = await params;
  const challenge = getChallengeById(challengeId);
  if (!challenge) notFound();

  return <PlayClient challenge={challenge} />;
}
