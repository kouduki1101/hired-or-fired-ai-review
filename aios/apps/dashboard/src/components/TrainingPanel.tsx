"use client";

// 学習系 Rehatch(蒸留/LoRA)進捗パネル(P5 / ¶0057「進捗可視化必須」)
// スロットを選んで蒸留ジョブを開始し、進捗バーで前進を可視化。
// 完了時に Rehatch-in-Place(世代+1)確定 or 検証不合格ロールバックを表示する。

import { useCallback, useEffect, useRef, useState } from "react";

import { api, type SlotSummary, type TrainingState } from "@/lib/api";

export function TrainingPanel({
  cohortId,
  slots,
  onDone,
}: {
  cohortId: string;
  slots: SlotSummary[];
  onDone: () => void;
}) {
  const [target, setTarget] = useState(slots[0]?.slot_id ?? "");
  const [job, setJob] = useState<TrainingState | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dispName = useCallback(
    (id: string) => slots.find((s) => s.slot_id === id)?.display_id ?? id.slice(0, 8),
    [slots],
  );

  const start = async () => {
    if (!target) return;
    setBusy(true);
    try {
      setJob(await api.trainRehatch(cohortId, target));
    } finally {
      setBusy(false);
    }
  };

  // ジョブが未適用の間、一定間隔で advance を叩いて前進させる(FakeTrainerはpollで進む)
  useEffect(() => {
    if (!job || job.applied) return;
    timer.current = setTimeout(async () => {
      const next = await api.advanceTraining(cohortId, job.slot_id, job.job_id);
      setJob(next);
      if (next.applied) onDone();
    }, 800);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [job, cohortId, onDone]);

  const running = job != null && !job.applied;
  const pct = job ? Math.round(job.progress * 100) : 0;

  return (
    <div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <select
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          disabled={running}
          aria-label="学習対象スロット"
        >
          {slots.map((s) => (
            <option key={s.slot_id} value={s.slot_id}>
              ID:{s.display_id}(G{s.generation})
            </option>
          ))}
        </select>
        <button className="primary" disabled={busy || running} onClick={() => void start()}>
          蒸留 Rehatch を開始
        </button>
        <span className="muted">
          学習中もスロットは稼働継続(シャドウ学習)。完了時に世代+1 で確定。
        </span>
      </div>

      {job && (
        <div style={{ marginTop: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
            <span>
              ID:{dispName(job.slot_id)} — <strong>{statusLabel(job)}</strong>
              {job.score != null && !job.applied ? `(見込み適合度 ${job.score.toFixed(2)})` : ""}
            </span>
            <span className="muted">step {job.step} / {pct}%</span>
          </div>
          <div className="fitbar" aria-hidden>
            <div
              style={{
                width: `${pct}%`,
                background: job.applied
                  ? job.committed
                    ? "var(--ok, #3fb950)"
                    : "var(--warn, #d29922)"
                  : undefined,
              }}
            />
          </div>
          {job.applied && (
            <p className="muted" style={{ marginBottom: 0, marginTop: 8 }}>
              {job.committed
                ? `✔ Rehatch-in-Place 確定 — ID:${dispName(job.slot_id)} は第${job.generation}世代へ(ID・履歴は維持)`
                : "✘ スモーク検証不合格 — 直前世代へロールバック"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function statusLabel(job: TrainingState): string {
  if (job.applied) return job.committed ? "確定" : "ロールバック";
  if (job.status === "succeeded") return "適用中";
  return "学習中";
}
