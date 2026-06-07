"use client";

import { getCodeLines } from "@/lib/gameEngine";
import type { InterviewChallenge } from "@/lib/types";

type Props = {
  challenge: InterviewChallenge;
  selectedLine: number | null;
  resolvedIssueIds: string[];
  onSelectLine: (lineNumber: number) => void;
};

export function CodeViewer({
  challenge,
  selectedLine,
  resolvedIssueIds,
  onSelectLine
}: Props) {
  const lines = getCodeLines(challenge.code);

  function isResolvedLine(lineNumber: number) {
    return challenge.issues.some((issue) => {
      return (
        resolvedIssueIds.includes(issue.id) &&
        lineNumber >= issue.startLine &&
        lineNumber <= issue.endLine
      );
    });
  }

  return (
    <section className="code-card" aria-label="AI Generated Code">
      <div className="code-header">
        <div>
          <strong>AI Generated Code</strong>
          <p className="muted" style={{ margin: 0 }}>
            Python / click a suspicious line
          </p>
        </div>
        <span className="pill dark">{lines.length} lines</span>
      </div>
      <div className="code-viewer" aria-label="Code lines">
        {lines.map((line, index) => {
          const lineNumber = index + 1;
          const selected = selectedLine === lineNumber;
          const resolved = isResolvedLine(lineNumber);
          return (
            <button
              className={`code-line${selected ? " selected" : ""}${
                resolved ? " resolved" : ""
              }`}
              key={`${lineNumber}-${line}`}
              type="button"
              aria-label={`Line ${lineNumber}: ${line || "blank"}`}
              aria-pressed={selected}
              onClick={() => onSelectLine(lineNumber)}
            >
              <span className="line-number">
                {resolved ? "✓" : lineNumber}
              </span>
              <span className="line-code">{line || " "}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
