"use client";

// スロット別詳細パネル(FR-UI-05 / 図16 1508)
// タイル: ID / 成熟度(Age) / 適合度(Fitness) / 状態。Rehatch直後(世代>0かつ成熟度0)は雛アイコン。
// クリックで運用履歴タイムライン(リネージAPI)を展開する。

import { useState } from "react";

import { api, type SlotHistory, type SlotSummary } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  ACTIVE: "稼働中",
  TRAINING: "学習中",
  REHATCHING: "再初期化中",
  QUARANTINED: "隔離中",
  DORMANT: "休止",
};

export function SlotTiles({ slots }: { slots: SlotSummary[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const [history, setHistory] = useState<SlotHistory | null>(null);

  const toggle = async (slotId: string) => {
    if (open === slotId) {
      setOpen(null);
      setHistory(null);
      return;
    }
    setOpen(slotId);
    setHistory(await api.slotHistory(slotId));
  };

  return (
    <div>
      <div className="tiles">
        {slots.map((s) => {
          const freshlyRehatched = s.generation > 0 && s.maturity === 0;
          return (
            <button
              key={s.slot_id}
              className={`tile ${s.status}`}
              style={{ textAlign: "left" }}
              onClick={() => toggle(s.slot_id)}
              aria-expanded={open === s.slot_id}
            >
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="id">
                  ID:{s.display_id} {freshlyRehatched ? "🐣" : ""}
                  {s.rehatch_lock ? "🔒" : ""}
                </span>
                <span className="muted">G{s.generation}</span>
              </div>
              <div className="muted">
                {STATUS_LABEL[s.status] ?? s.status} / Age {s.maturity}
              </div>
              <div className="muted">
                Fitness {s.fitness == null ? "—" : s.fitness.toFixed(2)}
              </div>
              <div className="fitbar" aria-hidden>
                <div style={{ width: `${((s.fitness ?? 0) * 100).toFixed(0)}%` }} />
              </div>
            </button>
          );
        })}
      </div>

      {open && history && (
        <div style={{ marginTop: 12 }}>
          <h2>
            運用履歴 — ID:{history.display_id}(第{history.current_generation}世代 /{" "}
            チェーン検証: {history.chain_verified ? "✔ 完全" : "✘ 不整合"})
          </h2>
          <div style={{ maxHeight: 220, overflowY: "auto" }}>
            <table className="events">
              <thead>
                <tr>
                  <th>時刻</th>
                  <th>世代</th>
                  <th>イベント</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                {history.events.map((e, i) => (
                  <tr key={i}>
                    <td className="muted">{e.occurred_at.slice(0, 19).replace("T", " ")}</td>
                    <td>G{e.generation}</td>
                    <td>{e.event_type}</td>
                    <td className="muted">{summarizePayload(e.payload)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function summarizePayload(payload: Record<string, unknown>): string {
  const parts = Object.entries(payload)
    .slice(0, 3)
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`);
  return parts.join(" ");
}
