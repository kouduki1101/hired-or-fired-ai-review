"use client";

// トレンド&追従グラフ(FR-UI-03 / 図16 1506)
// 太線 = 群平均(主系列)、細線 = 各スロットの軌跡(追従)。ホバーで値をツールチップ表示。

import { useMemo, useState } from "react";

export interface TrendSeries {
  /** 主系列(太線)。y は null 可(欠測サイクル) */
  main: { x: number; y: number | null }[];
  /** スロット別の細線(任意) */
  slots?: { label: string; points: { x: number; y: number | null }[] }[];
  yMax?: number;
}

const W = 560;
const H = 180;
const PAD = { left: 36, right: 10, top: 10, bottom: 22 };

export function TrendChart({ main, slots = [], yMax = 1.0 }: TrendSeries) {
  const [hover, setHover] = useState<number | null>(null);

  const xs = main.map((p) => p.x);
  const xMin = xs.length ? Math.min(...xs) : 0;
  const xMax = xs.length ? Math.max(...xs) : 1;
  const sx = (x: number) =>
    PAD.left + ((x - xMin) / Math.max(1, xMax - xMin)) * (W - PAD.left - PAD.right);
  const sy = (y: number) => PAD.top + (1 - Math.min(y, yMax) / yMax) * (H - PAD.top - PAD.bottom);

  const path = (pts: { x: number; y: number | null }[]) =>
    pts
      .filter((p): p is { x: number; y: number } => p.y != null)
      .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`)
      .join(" ");

  const hoverPoint = useMemo(() => {
    if (hover == null || !main.length) return null;
    const nearest = main.reduce((a, b) =>
      Math.abs(sx(b.x) - hover) < Math.abs(sx(a.x) - hover) ? b : a
    );
    return nearest.y == null ? null : nearest;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hover, main]);

  if (!main.length) return <p className="muted">サイクル未実行(「サイクル実行」で開始)</p>;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: "100%", height: "auto" }}
      onMouseMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        setHover(((e.clientX - rect.left) / rect.width) * W);
      }}
      onMouseLeave={() => setHover(null)}
      role="img"
      aria-label="群平均とスロット別の時系列"
    >
      {/* グリッド(控えめ) */}
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={sy(t * yMax)}
            y2={sy(t * yMax)}
            stroke="var(--border)"
            strokeWidth={1}
          />
          <text x={4} y={sy(t * yMax) + 4} fontSize={10} fill="var(--text-muted)">
            {(t * yMax).toFixed(1)}
          </text>
        </g>
      ))}
      {/* スロット別 細線(追従) */}
      {slots.map((s) => (
        <path
          key={s.label}
          d={path(s.points)}
          fill="none"
          stroke="var(--series-slot)"
          strokeWidth={1}
          opacity={0.6}
        />
      ))}
      {/* 主系列 太線 */}
      <path d={path(main)} fill="none" stroke="var(--series-1)" strokeWidth={2.5} />
      {/* ホバー: クロスヘア+ツールチップ */}
      {hoverPoint && (
        <g>
          <line
            x1={sx(hoverPoint.x)}
            x2={sx(hoverPoint.x)}
            y1={PAD.top}
            y2={H - PAD.bottom}
            stroke="var(--text-muted)"
            strokeDasharray="3 3"
          />
          <circle cx={sx(hoverPoint.x)} cy={sy(hoverPoint.y!)} r={4} fill="var(--series-1)" />
          <g transform={`translate(${Math.min(sx(hoverPoint.x) + 8, W - 120)}, ${PAD.top})`}>
            <rect width={110} height={34} rx={5} fill="var(--surface-3)" stroke="var(--border)" />
            <text x={8} y={14} fontSize={10} fill="var(--text-muted)">
              step {hoverPoint.x}
            </text>
            <text x={8} y={27} fontSize={12} fill="var(--text-primary)" fontWeight={700}>
              {hoverPoint.y!.toFixed(3)}
            </text>
          </g>
        </g>
      )}
      {/* X軸端ラベル */}
      <text x={PAD.left} y={H - 6} fontSize={10} fill="var(--text-muted)">
        step {xMin}
      </text>
      <text x={W - PAD.right} y={H - 6} fontSize={10} fill="var(--text-muted)" textAnchor="end">
        step {xMax}
      </text>
    </svg>
  );
}
