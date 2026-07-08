"use client";

// 群健全性ダッシュボード(明細書 図16 / FR-UI-01〜07)
// 1502 稼働ステータス / 1504 散逸度メーター / 1506 トレンド&追従 /
// 1508 スロットタイル / 1510 制御パラメータ / 1512 イベントログ + 操作系

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import { DissipationMeter, healthLabel } from "@/components/DissipationMeter";
import { SlotTiles } from "@/components/SlotTiles";
import { TrainingPanel } from "@/components/TrainingPanel";
import { TrendChart } from "@/components/TrendChart";
import { api, type Cohort, type CurrentMetrics, type CycleHistoryEntry } from "@/lib/api";

const POLL_MS = 2500;

export default function CohortDashboard({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [cohort, setCohort] = useState<Cohort | null>(null);
  const [metrics, setMetrics] = useState<CurrentMetrics | null>(null);
  const [history, setHistory] = useState<CycleHistoryEntry[]>([]);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [c, m, h] = await Promise.all([
      api.getCohort(id),
      api.currentMetrics(id),
      api.metricsHistory(id),
    ]);
    setCohort(c);
    setMetrics(m);
    setHistory(h);
  }, [id]);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  if (!cohort || !metrics) return <main className="page">読み込み中…</main>;

  const activeCount = cohort.slots.filter((s) => s.status === "ACTIVE").length;
  const paused = metrics.loop_state === "PAUSED";
  const dryRun = metrics.loop_state === "DRY_RUN";

  const fitnessMain = history.map((h) => ({ x: h.step_no, y: h.fitness_mean }));
  const slotSeries = (cohort.slots.slice(0, 12)).map((s) => ({
    label: s.display_id,
    points: history.map((h) => ({
      x: h.step_no,
      y: h.slots.find((x) => x.display_id === s.display_id)?.fitness ?? null,
    })),
  }));
  const dissipationMain = history.map((h) => ({ x: h.step_no, y: h.dissipation }));
  const dissipationMax = Math.max(metrics.thresholds.upper * 1.3, 1.0);

  return (
    <main className="page">
      {/* 1502 稼働ステータスヘッダ(FR-UI-01) */}
      <div className="panel" style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
          <Link href="/" className="muted">← 一覧</Link>
          <strong>{cohort.name || cohort.cohort_id}</strong>
          <span className={`badge ${paused ? "FIXED" : "STABLE"}`}>
            {paused ? "PAUSED" : dryRun ? "DRY-RUN" : "RUNNING"}
          </span>
          <span className="stat"><span className="value">{metrics.step_no}</span><span className="label">総稼働ステップ</span></span>
          <span className="stat"><span className="value">{activeCount}/{cohort.slot_count}</span><span className="label">稼働スロット(母集団)</span></span>
          <span style={{ flex: 1 }} />
          {/* FR-UI-07 操作系 */}
          <button className="primary" disabled={busy || paused} onClick={() => void act(() => api.runCycle(id))}>サイクル実行</button>
          <button disabled={busy} onClick={() => void act(() => api.controlLoop(id, paused ? "resume" : "pause"))}>{paused ? "再開" : "一時停止"}</button>
          <button disabled={busy} onClick={() => void act(() => api.controlLoop(id, dryRun ? "dry_run_off" : "dry_run_on"))}>{dryRun ? "dry-run解除" : "dry-run"}</button>
          <button disabled={busy} onClick={() => void act(() => api.submitTask(id, "high"))}>高重要度タスク投入</button>
          <button disabled={busy} onClick={() => void act(() => api.submitTask(id, "low"))}>探索タスク投入</button>
        </div>
      </div>

      <div className="grid">
        {/* 1504 散逸度メーター(FR-UI-02) */}
        <section className="panel" style={{ gridColumn: "span 5" }}>
          <h2>群全体のばらつき(散逸度)</h2>
          <DissipationMeter
            value={metrics.dissipation}
            lower={metrics.thresholds.lower}
            upper={metrics.thresholds.upper}
            health={metrics.health}
          />
        </section>

        {/* 1510 制御パラメータモニタ(FR-UI-04) */}
        <section className="panel" style={{ gridColumn: "span 7" }}>
          <h2>動的制御パラメータ(請求項7)</h2>
          <div style={{ display: "flex", gap: 32 }}>
            <span className="stat">
              <span className="value">×{metrics.dynamics.lr_correction.toFixed(2)}</span>
              <span className="label">学習率補正</span>
            </span>
            <span className="stat">
              <span className="value">{metrics.dynamics.noise_amount.toFixed(3)}</span>
              <span className="label">ノイズ付加量</span>
            </span>
            <span className="stat">
              <span className="value">{healthLabel(metrics.health)}</span>
              <span className="label">健全性判定</span>
            </span>
          </div>
          <p className="muted" style={{ marginBottom: 0 }}>
            固着時はノイズ・学習率を自動増加、過分散時は収束方向へ自動調整。
          </p>
        </section>

        {/* 1506 トレンド&追従グラフ(FR-UI-03) */}
        <section className="panel" style={{ gridColumn: "span 6" }}>
          <h2>適合度の推移 — 太線: 群平均 / 細線: 各スロット</h2>
          <TrendChart main={fitnessMain} slots={slotSeries} yMax={1.0} />
        </section>
        <section className="panel" style={{ gridColumn: "span 6" }}>
          <h2>散逸度の推移(第2の指標)</h2>
          <TrendChart main={dissipationMain} yMax={dissipationMax} />
        </section>

        {/* 1508 スロット別詳細パネル(FR-UI-05) */}
        <section className="panel" style={{ gridColumn: "span 12" }}>
          <h2>スロット(固定母集団 — 削除不可の管理単位)</h2>
          <SlotTiles slots={cohort.slots} />
        </section>

        {/* 学習系Rehatch(蒸留/LoRA)進捗(P5 / 進捗可視化必須) */}
        <section className="panel" style={{ gridColumn: "span 12" }}>
          <h2>学習系 Rehatch(蒸留)— 非同期ジョブ進捗</h2>
          <TrainingPanel cohortId={id} slots={cohort.slots} onDone={() => void refresh()} />
        </section>

        {/* 1512 イベントログ(FR-UI-06) */}
        <section className="panel" style={{ gridColumn: "span 12" }}>
          <h2>イベントログ</h2>
          <EventLog history={history} cohort={cohort} />
        </section>
      </div>
    </main>
  );
}

function EventLog({ history, cohort }: { history: CycleHistoryEntry[]; cohort: Cohort }) {
  const name = (slotId: string) =>
    cohort.slots.find((s) => s.slot_id === slotId)?.display_id ?? slotId.slice(0, 8);
  const items: { step: number; text: string; kind: string }[] = [];
  for (const h of history) {
    for (const q of h.quarantined) {
      items.push({ step: h.step_no, kind: "CHAOTIC", text: `ID:${name(q.slot_id)} を隔離(禁止ベクトル: ${q.label})` });
    }
    for (const r of h.rehatched) {
      items.push({
        step: h.step_no,
        kind: r.committed ? "STABLE" : "FIXED",
        text: r.committed
          ? `ID:${name(r.slot_id)} に Rehatch-in-Place を実行(理由: ${r.reason})`
          : `ID:${name(r.slot_id)} の Rehatch を検証不合格でロールバック(理由: ${r.reason})`,
      });
    }
    if (h.health === "FIXED") items.push({ step: h.step_no, kind: "FIXED", text: "固着検知: ノイズ注入中" });
    if (h.health === "CHAOTIC") items.push({ step: h.step_no, kind: "CHAOTIC", text: "過分散検知: 学習率抑制中" });
  }
  const recent = items.slice(-30).reverse();
  if (!recent.length) return <p className="muted">イベントはまだありません</p>;
  return (
    <ul className="log">
      {recent.map((e, i) => (
        <li key={i}>
          <span className="step">[step {e.step}]</span>
          <span className={`badge ${e.kind}`} style={{ fontSize: 10 }}>{e.kind}</span>
          <span>{e.text}</span>
        </li>
      ))}
    </ul>
  );
}
