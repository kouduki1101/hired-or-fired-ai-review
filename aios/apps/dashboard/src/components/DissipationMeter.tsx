"use client";

// 散逸度メーター(FR-UI-02 / 図16 1504)
// 3ゾーン(FIXED/STABLE/CHAOTIC)は色+ラベル+マーカー形状で示す(色のみに依存しない)

import type { Health } from "@/lib/api";

export function DissipationMeter(props: {
  value: number | null;
  lower: number;
  upper: number;
  health: Health;
}) {
  const { value, lower, upper, health } = props;
  const max = Math.max(upper * 1.3, value ?? 0, 1.0);
  const pct = (x: number) => `${Math.min(100, (x / max) * 100)}%`;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <span className={`badge ${health}`}>{healthLabel(health)}</span>
        <span className="stat" style={{ alignItems: "flex-end" }}>
          <span className="value">{value == null ? "—" : value.toFixed(3)}</span>
          <span className="label">第2の指標(散逸度)</span>
        </span>
      </div>
      <div
        role="meter"
        aria-label="散逸度"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value ?? undefined}
        style={{
          position: "relative",
          height: 22,
          borderRadius: 6,
          overflow: "hidden",
          border: "1px solid var(--border)",
        }}
      >
        <Zone left="0%" width={pct(lower)} color="var(--status-fixed)" />
        <Zone left={pct(lower)} width={`calc(${pct(upper)} - ${pct(lower)})`} color="var(--status-stable)" />
        <Zone left={pct(upper)} width={`calc(100% - ${pct(upper)})`} color="var(--status-chaotic)" />
        {value != null && (
          <div
            style={{
              position: "absolute",
              left: pct(value),
              top: 0,
              bottom: 0,
              width: 3,
              background: "var(--text-primary)",
            }}
          />
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }} className="muted">
        <span>固着 FIXED（&lt; {lower}）</span>
        <span>安定 STABLE</span>
        <span>カオス CHAOTIC（&gt; {upper}）</span>
      </div>
    </div>
  );
}

function Zone({ left, width, color }: { left: string; width: string; color: string }) {
  return (
    <div
      style={{
        position: "absolute",
        left,
        width,
        top: 0,
        bottom: 0,
        background: color,
        opacity: 0.35,
      }}
    />
  );
}

export function healthLabel(h: Health): string {
  return { FIXED: "固着", STABLE: "安定", CHAOTIC: "カオス", UNKNOWN: "未観測" }[h];
}
