import type {
  InterviewChallenge,
  ReviewIssue,
  ReviewStepKind
} from "@/lib/types";

export function getCodeLines(code: string): string[] {
  return code.replace(/\r\n/g, "\n").split("\n");
}

export function getIssueForLine(
  challenge: InterviewChallenge,
  lineNumber: number,
  resolvedIssueIds: string[] = []
): ReviewIssue | undefined {
  return challenge.issues.find((issue) => {
    const unresolved = !resolvedIssueIds.includes(issue.id);
    return unresolved && lineNumber >= issue.startLine && lineNumber <= issue.endLine;
  });
}

export function isIssueResolved(issueId: string, resolvedIssueIds: string[]) {
  return resolvedIssueIds.includes(issueId);
}

export function areAllIssuesResolved(
  challenge: InterviewChallenge,
  resolvedIssueIds: string[]
): boolean {
  return challenge.issues.every((issue) => resolvedIssueIds.includes(issue.id));
}

export function getCorrectChoiceId(issue: ReviewIssue, kind: ReviewStepKind) {
  const step = issue.steps.find((item) => item.kind === kind);
  return step?.choices.find((choice) => choice.correct)?.id;
}

export function isCorrectChoice(
  issue: ReviewIssue,
  kind: ReviewStepKind,
  choiceId: string
): boolean {
  return getCorrectChoiceId(issue, kind) === choiceId;
}

export function getNextUnresolvedIssue(
  challenge: InterviewChallenge,
  resolvedIssueIds: string[]
): ReviewIssue | undefined {
  return challenge.issues.find((issue) => !resolvedIssueIds.includes(issue.id));
}
