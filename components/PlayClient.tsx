"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { categoryLabels } from "@/data/challenges";
import { CodeViewer } from "@/components/CodeViewer";
import { SoundToggle } from "@/components/SoundToggle";
import {
  areAllIssuesResolved,
  getIssueForLine,
  getNextUnresolvedIssue
} from "@/lib/gameEngine";
import {
  SCORE,
  clampScore,
  createEmptyCategoryStats,
  getCorrectStepScore,
  getHintPenalty,
  getHiringRank,
  getMaxPossibleScore,
  getReviewRate,
  getReviewerType,
  getWrongStepPenalty
} from "@/lib/scoring";
import { playClear, playCorrect, playWrong, primeAudio } from "@/lib/sound";
import {
  loadSoundEnabled,
  saveLastResult,
  saveSoundEnabled,
  updateChallengeRecord
} from "@/lib/storage";
import type {
  CategoryStats,
  FoundIssue,
  GameResult,
  InterviewChallenge,
  ReviewIssue,
  ReviewStep,
  ReviewStepKind,
  WrongAttempt,
  WrongAttemptReason
} from "@/lib/types";

type Props = {
  challenge: InterviewChallenge;
};

const stepLabels: Record<ReviewStepKind, string> = {
  category: "Issue Category / 不具合カテゴリ",
  pattern: "Failure Pattern / 失敗パターン",
  fix: "Correct Fix / 正しい修正"
};

const wrongReasonByStep: Record<ReviewStepKind, WrongAttemptReason> = {
  category: "wrong_category",
  pattern: "wrong_pattern",
  fix: "wrong_fix"
};

function cloneStats(stats: CategoryStats): CategoryStats {
  return {
    spec: { ...stats.spec },
    logic: { ...stats.logic },
    boundary: { ...stats.boundary },
    data_flow: { ...stats.data_flow },
    security: { ...stats.security }
  };
}

export function PlayClient({ challenge }: Props) {
  const router = useRouter();
  const [started, setStarted] = useState(false);
  const [finished, setFinished] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [remaining, setRemaining] = useState(challenge.timeLimitSeconds);
  const [score, setScore] = useState(0);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [resolvedIssueIds, setResolvedIssueIds] = useState<string[]>([]);
  const [foundIssues, setFoundIssues] = useState<FoundIssue[]>([]);
  const [wrongAttempts, setWrongAttempts] = useState<WrongAttempt[]>([]);
  const [hintsUsed, setHintsUsed] = useState(0);
  const [issueHintLevel, setIssueHintLevel] = useState<Record<string, number>>(
    {}
  );
  const [hintCursor, setHintCursor] = useState(0);
  const [hintMessages, setHintMessages] = useState<string[]>([]);
  const [feedback, setFeedback] = useState(
    "要件とコードを読んでから、レビュー開始を押してください。"
  );
  const [categoryStats, setCategoryStats] = useState<CategoryStats>(
    createEmptyCategoryStats
  );
  const [soundEnabled, setSoundEnabled] = useState(true);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSoundEnabled(loadSoundEnabled());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const activeIssue = useMemo(() => {
    return challenge.issues.find((issue) => issue.id === activeIssueId);
  }, [activeIssueId, challenge.issues]);

  const activeStep: ReviewStep | undefined = activeIssue?.steps[stepIndex];
  const nextIssue = getNextUnresolvedIssue(challenge, resolvedIssueIds);
  const maxScore = getMaxPossibleScore(challenge);
  const scoreRate = Math.max(0, Math.min(1, score / maxScore));
  const nextHintTarget = (() => {
    const unresolvedIssues = challenge.issues.filter(
      (issue) => !resolvedIssueIds.includes(issue.id)
    );
    if (unresolvedIssues.length === 0) return undefined;

    for (let offset = 0; offset < unresolvedIssues.length; offset += 1) {
      const index = (hintCursor + offset) % unresolvedIssues.length;
      const issue = unresolvedIssues[index];
      const level = issueHintLevel[issue.id] ?? 0;
      if (level < issue.hints.length) {
        return {
          issue,
          level,
          nextCursor: (index + 1) % unresolvedIssues.length
        };
      }
    }

    return undefined;
  })();

  const finishGame = useCallback(
    (
      finalScore: number,
      finalResolvedIds: string[],
      finalWrongAttempts: WrongAttempt[],
      finalHintsUsed: number,
      finalCategoryStats: CategoryStats
    ) => {
      if (finished) return;
      setFinished(true);
      const finalMaxScore = getMaxPossibleScore(challenge);
      const rank = getHiringRank(finalScore, finalMaxScore);
      const elapsedSeconds =
        startedAt === null
          ? 0
          : Math.min(
              challenge.timeLimitSeconds,
              Math.floor((Date.now() - startedAt) / 1000)
            );

      const result: GameResult = {
        challengeId: challenge.id,
        finalScore,
        maxScore: finalMaxScore,
        scoreRate: finalMaxScore <= 0 ? 0 : finalScore / finalMaxScore,
        rank,
        reviewRate: getReviewRate(rank),
        reviewerType: getReviewerType(finalCategoryStats),
        foundIssueIds: finalResolvedIds,
        missedIssueIds: challenge.issues
          .filter((issue) => !finalResolvedIds.includes(issue.id))
          .map((issue) => issue.id),
        wrongAttempts: finalWrongAttempts,
        hintsUsed: finalHintsUsed,
        elapsedSeconds,
        categoryStats: finalCategoryStats,
        finishedAt: new Date().toISOString()
      };

      saveLastResult(result);
      updateChallengeRecord(result);
      router.push("/result");
    },
    [challenge, finished, router, startedAt]
  );

  useEffect(() => {
    if (!started || startedAt === null || finished) return;

    const timer = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      const nextRemaining = Math.max(0, challenge.timeLimitSeconds - elapsed);
      setRemaining(nextRemaining);
      if (nextRemaining === 0) {
        window.clearInterval(timer);
        finishGame(score, resolvedIssueIds, wrongAttempts, hintsUsed, categoryStats);
      }
    }, 250);

    return () => window.clearInterval(timer);
  }, [
    categoryStats,
    challenge.timeLimitSeconds,
    finishGame,
    finished,
    hintsUsed,
    resolvedIssueIds,
    score,
    started,
    startedAt,
    wrongAttempts
  ]);

  function updateSound(enabled: boolean) {
    setSoundEnabled(enabled);
    saveSoundEnabled(enabled);
  }

  function startInterview() {
    primeAudio();
    setStarted(true);
    setStartedAt(Date.now());
    setFeedback("レビュー開始。怪しい行を選んで指摘してください。");
  }

  function handleSelectLine(lineNumber: number) {
    if (activeIssue) {
      setFeedback("先にいまの指摘を最後まで確定してください。");
      return;
    }

    setSelectedLine(lineNumber);
    setFeedback(
      started
        ? "その行を本当に指摘するなら、右パネルで確定してください。"
        : "開始前に行を見ることはできます。採点はレビュー開始後です。"
    );
  }

  function recordCategoryAttempt(
    issue: ReviewIssue,
    correct: boolean,
    currentStats = categoryStats
  ) {
    const nextStats = cloneStats(currentStats);
    nextStats[issue.category].attempts += 1;
    if (correct) nextStats[issue.category].correct += 1;
    setCategoryStats(nextStats);
    return nextStats;
  }

  function addWrongAttempt(attempt: WrongAttempt) {
    const nextAttempts = [attempt, ...wrongAttempts];
    setWrongAttempts(nextAttempts);
    return nextAttempts;
  }

  function confirmSelectedLine() {
    if (!started || selectedLine === null) return;

    const issue = getIssueForLine(challenge, selectedLine, resolvedIssueIds);
    if (issue) {
      setActiveIssueId(issue.id);
      setStepIndex(0);
      setFeedback("指摘を受け付けました。まずカテゴリを選んでください。");
      return;
    }

    const penalty = SCORE.wrongLine;
    const nextScore = clampScore(score + penalty);
    const nextAttempts = addWrongAttempt({
      line: selectedLine,
      reason: "not_an_issue",
      message: `${selectedLine}行目は今回の隠しIssueではありません。`
    });
    setScore(nextScore);
    setSelectedLine(null);
    setFeedback(`${selectedLine}行目は不正解。${penalty}点`);
    playWrong(soundEnabled);
    return nextAttempts;
  }

  function useNextBugHint() {
    if (!started || !nextHintTarget) return;
    const { issue, level, nextCursor } = nextHintTarget;
    const penalty = getHintPenalty(level);
    setScore((current) => clampScore(current + penalty));
    setHintsUsed((current) => current + 1);
    setHintMessages((messages) => [
      `Hint ${messages.length + 1}: ${issue.hints[level]} (${penalty}点)`,
      ...messages
    ]);
    setIssueHintLevel((levels) => ({
      ...levels,
      [issue.id]: level + 1
    }));
    setHintCursor(nextCursor);
    playWrong(soundEnabled);
  }

  function handleChoice(choiceId: string) {
    if (!started || !activeIssue || !activeStep) return;
    const choice = activeStep.choices.find((item) => item.id === choiceId);
    if (!choice) return;

    const correct = choice.correct;
    const delta = correct
      ? getCorrectStepScore(activeStep.kind, activeIssue.difficulty)
      : getWrongStepPenalty(activeStep.kind);
    let nextScore = clampScore(score + delta);
    const nextStats = recordCategoryAttempt(activeIssue, correct);

    if (!correct) {
      const nextAttempts = addWrongAttempt({
        issueId: activeIssue.id,
        line: selectedLine ?? activeIssue.startLine,
        reason: wrongReasonByStep[activeStep.kind],
        message: `${activeIssue.title}: ${stepLabels[activeStep.kind]} が違います。`
      });
      setScore(nextScore);
      setFeedback(`惜しい。${stepLabels[activeStep.kind]} を見直そう。${delta}点`);
      playWrong(soundEnabled);
      return nextAttempts;
    }

    if (activeStep.kind !== "fix") {
      setScore(nextScore);
      setStepIndex((index) => index + 1);
      setFeedback(`正解。${stepLabels[activeStep.kind]} +${delta}点`);
      playCorrect(soundEnabled);
      return;
    }

    const nextResolvedIds = [...resolvedIssueIds, activeIssue.id];
    const nextFoundIssues = [
      {
        issueId: activeIssue.id,
        foundAtSeconds: challenge.timeLimitSeconds - remaining,
        scoreDelta: delta
      },
      ...foundIssues
    ];
    setResolvedIssueIds(nextResolvedIds);
    setFoundIssues(nextFoundIssues);
    setActiveIssueId(null);
    setSelectedLine(null);
    setStepIndex(0);
    setScore(nextScore);
    setFeedback(`Issue resolved: ${activeIssue.title} +${delta}点`);
    playCorrect(soundEnabled);

    if (areAllIssuesResolved(challenge, nextResolvedIds)) {
      const noMissBonus = wrongAttempts.length === 0 ? SCORE.noMissBonus : 0;
      const bonus =
        SCORE.completionBonus +
        noMissBonus +
        remaining * SCORE.timeBonusPerSecond;
      nextScore = clampScore(nextScore + bonus);
      setScore(nextScore);
      playClear(soundEnabled);
      finishGame(
        nextScore,
        nextResolvedIds,
        wrongAttempts,
        hintsUsed,
        nextStats
      );
    }
  }

  function manualFinish() {
    finishGame(score, resolvedIssueIds, wrongAttempts, hintsUsed, categoryStats);
  }

  return (
    <main>
      <div className="section-header">
        <div>
          <p className="eyebrow">Review Interview</p>
          <h1 className="section-title">{challenge.title}</h1>
          <p className="muted">
            {challenge.role} / {challenge.difficultyLabel}
          </p>
        </div>
        <div className="nav-links">
          <SoundToggle enabled={soundEnabled} onChange={updateSound} />
          <button className="danger-button" type="button" onClick={manualFinish}>
            面接を終了
          </button>
        </div>
      </div>

      <div className="play-layout">
        <aside className="light-card">
          <h2 style={{ marginTop: 0 }}>Interview Brief</h2>
          <div className="metric-grid">
            <div className="metric light">
              <span className="panel-muted">Time</span>
              <b>
                {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}
              </b>
            </div>
            <div className="metric light">
              <span className="panel-muted">Score</span>
              <b>{score}</b>
            </div>
            <div className="metric light">
              <span className="panel-muted">Issues</span>
              <b>
                {resolvedIssueIds.length}/{challenge.issues.length}
              </b>
            </div>
            <div className="metric light">
              <span className="panel-muted">Rate</span>
              <b>{Math.round(scoreRate * 100)}%</b>
            </div>
          </div>

          {!started ? (
            <button
              className="primary-button"
              type="button"
              style={{ width: "100%", marginTop: 16 }}
              onClick={startInterview}
            >
              レビュー開始
            </button>
          ) : (
            <div className="metric light" style={{ marginTop: 16 }}>
              <span className="panel-muted">Hint</span>
              <b style={{ fontSize: "1rem" }}>右パネルから1つずつ表示</b>
            </div>
          )}

          <h3>Requirements</h3>
          <ul className="brief-list">
            {challenge.requirements.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <h3>Examples</h3>
          <ul className="brief-list">
            {challenge.examples.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <h3>Constraints</h3>
          <ul className="brief-list">
            {challenge.constraints.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </aside>

        <CodeViewer
          challenge={challenge}
          selectedLine={selectedLine}
          resolvedIssueIds={resolvedIssueIds}
          onSelectLine={handleSelectLine}
        />

        <aside className="decision-panel">
          <section className="light-card">
            <h2 style={{ marginTop: 0 }}>Review Decision</h2>
            <p className="panel-muted">{feedback}</p>

            {selectedLine !== null && (
              <div className="metric light">
                <span className="panel-muted">Selected line</span>
                <b>{selectedLine}</b>
              </div>
            )}

            <div
              className="metric light"
              style={{ display: "grid", gap: 10, marginTop: 12 }}
            >
              <div>
                <strong>Hint Center</strong>
                <p className="panel-muted" style={{ margin: "4px 0 0" }}>
                  未解決バグのHintを1つずつ表示します。押すたびに減点されます。
                </p>
              </div>
              <button
                className="soft-button"
                type="button"
                style={{ width: "100%", color: "#172033" }}
                onClick={useNextBugHint}
                disabled={!started || !nextHintTarget}
              >
                次のHintを表示
                {started && nextHintTarget
                  ? ` (${getHintPenalty(nextHintTarget.level)}点)`
                  : ""}
              </button>
              {hintMessages.length > 0 && (
                <div className="log-list" style={{ maxHeight: 180 }}>
                  {hintMessages.slice(0, 5).map((message, index) => (
                    <div className="log-item light" key={`${message}-${index}`}>
                      {message}
                    </div>
                  ))}
                </div>
              )}
              {!started && (
                <p className="panel-muted" style={{ margin: 0 }}>
                  レビュー開始後に有効になります。
                </p>
              )}
              {started && !nextHintTarget && (
                <p className="panel-muted" style={{ margin: 0 }}>
                  表示できるHintはもうありません。
                </p>
              )}
            </div>

            {!started && (
              <p className="panel-muted">
                まず左の要件と中央のコードを読んでください。開始後に指摘が採点されます。
              </p>
            )}

            {started && selectedLine !== null && !activeIssue && (
              <button
                className="danger-button"
                type="button"
                style={{ width: "100%" }}
                onClick={confirmSelectedLine}
              >
                この行を指摘する
              </button>
            )}

            {started && activeIssue && activeStep && (
              <>
                <div style={{ marginTop: 14 }}>
                  <span className="pill">{categoryLabels[activeIssue.category]}</span>
                  <h3 style={{ marginBottom: 4 }}>{stepLabels[activeStep.kind]}</h3>
                  <p className="panel-muted">{activeStep.prompt}</p>
                </div>

                <div className="choice-grid">
                  {activeStep.choices.map((choice) => (
                    <button
                      className="choice-button"
                      key={choice.id}
                      type="button"
                      onClick={() => handleChoice(choice.id)}
                    >
                      <strong>{choice.label}</strong>
                      <span>{choice.description}</span>
                      {choice.code && <pre className="code-choice">{choice.code}</pre>}
                    </button>
                  ))}
                </div>

              </>
            )}
          </section>

          <section className="dark-card">
            <h3 style={{ marginTop: 0 }}>Found Issue Log</h3>
            <div className="log-list">
              {foundIssues.length === 0 && (
                <div className="log-item">まだIssueは解決されていません。</div>
              )}
              {foundIssues.map((found) => {
                const issue = challenge.issues.find(
                  (item) => item.id === found.issueId
                );
                return (
                  <div className="log-item" key={found.issueId}>
                    <span className="score-pop">Resolved</span> {issue?.title}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="dark-card">
            <h3 style={{ marginTop: 0 }}>Hints / Miss Log</h3>
            <div className="log-list">
              {[...hintMessages, ...wrongAttempts.map((item) => item.message)]
                .slice(0, 8)
                .map((item, index) => (
                  <div className="log-item" key={`${item}-${index}`}>
                    {item}
                  </div>
                ))}
              {hintMessages.length === 0 && wrongAttempts.length === 0 && (
                <div className="log-item">
                  ミスとヒント使用はここに記録されます。
                </div>
              )}
            </div>
          </section>

          {nextIssue && (
            <section className="dark-card">
              <h3 style={{ marginTop: 0 }}>Next target</h3>
              <p className="muted">
                未解決Issueはあと {challenge.issues.length - resolvedIssueIds.length} 件。
                詰まったらHintを使ってもOKです。
              </p>
            </section>
          )}
        </aside>
      </div>
    </main>
  );
}
