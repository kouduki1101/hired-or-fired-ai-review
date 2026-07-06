"use client";

// コホート一覧 + 作成(卵層の起動)

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, type Cohort } from "@/lib/api";

export default function Home() {
  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [name, setName] = useState("support-agents");
  const [slotCount, setSlotCount] = useState(10);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setCohorts(await api.listCohorts());
      setError(null);
    } catch (e) {
      setError(`APIに接続できません: ${(e as Error).message}`);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = async () => {
    await api.createCohort(name, slotCount);
    await refresh();
  };

  return (
    <main className="page">
      <h1 style={{ fontSize: 20 }}>AIOS — マルチエージェント群 長期運用基盤</h1>
      <p className="muted">
        コホート(固定母集団)を作成すると、卵層がK体のエージェントを生成し定常運用フェーズへ移行します(請求項10)。
      </p>
      {error && <p style={{ color: "var(--status-chaotic)" }}>{error}</p>}

      <div className="panel" style={{ marginBottom: 16 }}>
        <h2>新規コホート(卵層の起動)</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="名前" />
          <input
            type="number"
            min={2}
            max={1000}
            value={slotCount}
            onChange={(e) => setSlotCount(Number(e.target.value))}
            style={{ width: 90 }}
          />
          <button className="primary" onClick={() => void create()}>
            生成(K={slotCount})
          </button>
        </div>
      </div>

      <div className="panel">
        <h2>コホート一覧</h2>
        {cohorts.length === 0 && <p className="muted">まだありません</p>}
        <ul className="log">
          {cohorts.map((c) => (
            <li key={c.cohort_id}>
              <Link href={`/cohorts/${c.cohort_id}`}>{c.name || c.cohort_id}</Link>
              <span className="muted">
                {c.phase} / {c.slot_count} slots
              </span>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
