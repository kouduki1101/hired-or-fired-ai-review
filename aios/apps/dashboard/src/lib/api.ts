// AIOS Control Plane API クライアント(docs/05準拠の型付きfetch)

const BASE = process.env.NEXT_PUBLIC_AIOS_API ?? "http://localhost:8080";

export type SlotStatus = "ACTIVE" | "TRAINING" | "REHATCHING" | "QUARANTINED" | "DORMANT";
export type Health = "FIXED" | "STABLE" | "CHAOTIC" | "UNKNOWN";

export interface SlotSummary {
  slot_id: string;
  display_id: string;
  status: SlotStatus;
  generation: number;
  maturity: number;
  fitness: number | null;
  rehatch_lock: boolean;
}

export interface Cohort {
  cohort_id: string;
  name: string;
  phase: string;
  slot_count: number;
  slots: SlotSummary[];
}

export interface CurrentMetrics {
  cohort_id: string;
  step_no: number;
  loop_state: "RUNNING" | "PAUSED" | "DRY_RUN";
  health: Health;
  dissipation: number | null;
  dynamics: { lr_correction: number; noise_amount: number };
  thresholds: { lower: number; upper: number };
}

export interface CycleHistoryEntry {
  step_no: number;
  health: Health;
  dissipation: number | null;
  fitness_mean: number | null;
  lr_correction: number;
  noise_amount: number;
  rehatched: { slot_id: string; reason: string; committed: boolean }[];
  quarantined: { slot_id: string; label: string }[];
  slots: { display_id: string; fitness: number | null }[];
}

export interface TrainingState {
  job_id: string;
  slot_id: string;
  status: string;
  progress: number;
  step: number;
  message?: string;
  score?: number | null;
  applied?: boolean;
  committed?: boolean | null;
  generation?: number | null;
}

export interface SlotHistory {
  slot_id: string;
  display_id: string;
  current_generation: number;
  chain_verified: boolean;
  events: {
    event_type: string;
    generation: number;
    payload: Record<string, unknown>;
    occurred_at: string;
    hash: string;
  }[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  listCohorts: () => req<Cohort[]>("/v1/cohorts"),
  getCohort: (id: string) => req<Cohort>(`/v1/cohorts/${id}`),
  createCohort: (name: string, slotCount: number) =>
    req<Cohort>("/v1/cohorts", {
      method: "POST",
      body: JSON.stringify({ name, slot_count: slotCount }),
    }),
  currentMetrics: (id: string) => req<CurrentMetrics>(`/v1/cohorts/${id}/metrics/current`),
  metricsHistory: (id: string) => req<CycleHistoryEntry[]>(`/v1/cohorts/${id}/metrics/history`),
  runCycle: (id: string) => req(`/v1/cohorts/${id}/cycles/run`, { method: "POST" }),
  controlLoop: (id: string, action: string) =>
    req(`/v1/cohorts/${id}/loop`, { method: "POST", body: JSON.stringify({ action }) }),
  submitTask: (id: string, importance: string) =>
    req(`/v1/cohorts/${id}/tasks`, {
      method: "POST",
      body: JSON.stringify({
        input: { messages: [{ role: "user", content: "demo task" }] },
        metadata: { importance },
      }),
    }),
  slotHistory: (slotId: string) => req<SlotHistory>(`/v1/lineage/slots/${slotId}/history`),
  trainRehatch: (id: string, slotId: string, maxSteps = 8) =>
    req<TrainingState>(`/v1/cohorts/${id}/slots/${slotId}/rehatch/train`, {
      method: "POST",
      body: JSON.stringify({ strategy: "distillation", max_steps: maxSteps }),
    }),
  advanceTraining: (id: string, slotId: string, jobId: string) =>
    req<TrainingState>(`/v1/cohorts/${id}/slots/${slotId}/rehatch/train/${jobId}/advance`, {
      method: "POST",
    }),
};
