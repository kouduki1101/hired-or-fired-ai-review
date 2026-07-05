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

    # --- 制御サイクル結果 ---
    def set_last_cycle(self, cohort_id: str, result: CycleResult) -> None:
        self._last_cycle[cohort_id] = result

    def last_cycle(self, cohort_id: str) -> CycleResult | None:
        return self._last_cycle.get(cohort_id)


STORE = DemoStore()
