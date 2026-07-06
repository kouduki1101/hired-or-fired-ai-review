"""P1デモストア: CohortRuntime(インメモリ)+FakeAdapterで制御ループ一式をAPIから体験できる。

P2でpackages/storage(PostgreSQL)ベースの実装に置換する。境界:
- get_cohort / create_cohort / list_cohorts のシグネチャを維持する
- ルータはCohortRuntimeの内部構造に触れず、この層の関数を経由する
"""

from __future__ import annotations

import numpy as np
from aios_adapters.fake import FakeAgentAdapter
from aios_core.types import HealthThresholds
from aios_orchestrator.cycle import CycleResult
from aios_orchestrator.runtime import CohortRuntime, hatch_cohort
from fastapi import HTTPException

DEMO_DIM = 16
DEMO_THRESHOLDS = HealthThresholds(lower=0.05, upper=1.2, hysteresis_cycles=2)


class DemoStore:
    def __init__(self) -> None:
        self._cohorts: dict[str, CohortRuntime] = {}
        self._task_counts: dict[str, dict[str, int]] = {}  # cohort_id -> slot_id -> count
        self._last_cycle: dict[str, CycleResult] = {}
        self._task_records: dict[str, dict] = {}  # task_id -> リネージ記録(FR-GV-01)
        self._loop_states: dict[str, str] = {}  # cohort_id -> RUNNING/PAUSED/DRY_RUN
        self._cycle_history: dict[str, list[dict]] = {}  # cohort_id -> サイクル時系列

    def create_cohort(self, *, name: str, slot_count: int, ema_alpha: float) -> CohortRuntime:
        rng = np.random.default_rng(abs(hash(name)) % (2**32))
        t0 = rng.normal(size=DEMO_DIM)
        cohort = hatch_cohort(
            adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=i),
            slot_count=slot_count,
            initial_tv=t0,
            thresholds=DEMO_THRESHOLDS,
            diversity=0.4,
            seed=42,
            ema_alpha=ema_alpha,
        )
        self._cohorts[cohort.cohort_id] = cohort
        self._task_counts[cohort.cohort_id] = {s.slot_id: 0 for s in cohort.slots}
        return cohort

    def get_cohort(self, cohort_id: str) -> CohortRuntime:
        cohort = self._cohorts.get(cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        return cohort

    def list_cohorts(self) -> list[CohortRuntime]:
        return list(self._cohorts.values())

    # --- タスク割当シェア(支配的モデル検出の入力) ---
    def record_assignment(self, cohort_id: str, slot_id: str) -> None:
        counts = self._task_counts[cohort_id]
        counts[slot_id] = counts.get(slot_id, 0) + 1
        total = sum(counts.values())
        for s in self.get_cohort(cohort_id).slots:
            s.assign_share = counts.get(s.slot_id, 0) / total if total else 0.0

    # --- 制御サイクル結果(最新+履歴。履歴はダッシュボードのトレンド入力) ---
    def set_last_cycle(self, cohort_id: str, result: CycleResult) -> None:
        self._last_cycle[cohort_id] = result
        cohort = self.get_cohort(cohort_id)
        history = self._cycle_history.setdefault(cohort_id, [])
        history.append(
            {
                "step_no": result.step_no,
                "health": str(result.health),
                "dissipation": None if result.dissipation != result.dissipation
                else result.dissipation,  # NaN→None
                "fitness_mean": None if result.fitness_mean != result.fitness_mean
                else result.fitness_mean,
                "lr_correction": result.lr_correction,
                "noise_amount": result.noise_amount,
                "rehatched": [
                    {"slot_id": o.slot_id, "reason": o.reason, "committed": o.committed}
                    for o in result.rehatched
                ],
                "quarantined": [
                    {"slot_id": q.slot_id, "label": q.label} for q in result.quarantined
                ],
                "slots": [
                    {"display_id": s.display_id, "fitness": s.fitness_hat}
                    for s in cohort.slots
                ],
            }
        )
        del history[:-200]  # 直近200サイクルのみ保持(P2のPostgreSQL化で全履歴へ)

    def last_cycle(self, cohort_id: str) -> CycleResult | None:
        return self._last_cycle.get(cohort_id)

    def cycle_history(self, cohort_id: str) -> list[dict]:
        return self._cycle_history.get(cohort_id, [])

    # --- タスクリネージ記録(FR-GV-01: 担当時点の世代・判断・制御値を固定) ---
    def record_task(self, task_id: str, record: dict) -> None:
        self._task_records[task_id] = record

    def get_task(self, task_id: str) -> dict:
        record = self._task_records.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task not found")
        return record

    # --- ループ制御(FR-LC-03) ---
    def loop_state(self, cohort_id: str) -> str:
        return self._loop_states.get(cohort_id, "RUNNING")

    def set_loop_state(self, cohort_id: str, state: str) -> None:
        self._loop_states[cohort_id] = state

    def find_cohort_by_slot(self, slot_id: str) -> CohortRuntime:
        for cohort in self._cohorts.values():
            if any(s.slot_id == slot_id for s in cohort.slots):
                return cohort
        raise HTTPException(status_code=404, detail="slot not found")


STORE = DemoStore()
