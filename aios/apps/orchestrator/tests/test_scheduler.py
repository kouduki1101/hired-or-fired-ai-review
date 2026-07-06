"""CycleScheduler の周期駆動・pause/resume/dry-run・グレースフル停止。"""

from __future__ import annotations

import asyncio

import numpy as np
from aios_adapters.fake import FakeAgentAdapter
from aios_core.types import HealthThresholds
from aios_orchestrator.cycle import CycleResult
from aios_orchestrator.runtime import CohortRuntime, hatch_cohort
from aios_orchestrator.scheduler import CycleScheduler, LoopState


def make_cohort() -> CohortRuntime:
    t0 = np.random.default_rng(1).normal(size=8)
    return hatch_cohort(
        adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=i),
        slot_count=4,
        initial_tv=t0,
        thresholds=HealthThresholds(lower=0.05, upper=1.2),
        seed=3,
    )


async def wait_for(predicate, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


class TestScheduler:
    async def test_periodic_execution(self) -> None:
        cohort = make_cohort()
        results: list[CycleResult] = []
        sched = CycleScheduler(cohort, interval_seconds=0.02, on_result=results.append)
        sched.start()
        await wait_for(lambda: cohort.step_no >= 3)
        await sched.stop()
        assert sched.state == LoopState.STOPPED
        assert len(results) >= 3
        assert [r.step_no for r in results[:3]] == [1, 2, 3]  # 単調増加

    async def test_pause_stops_cycles_resume_restarts(self) -> None:
        cohort = make_cohort()
        sched = CycleScheduler(cohort, interval_seconds=0.02)
        sched.start()
        await wait_for(lambda: cohort.step_no >= 1)

        sched.pause()
        await asyncio.sleep(0.02)  # 実行中サイクルの完了猶予
        frozen = cohort.step_no
        await asyncio.sleep(0.1)
        assert cohort.step_no == frozen  # PAUSED中は進まない

        sched.resume()
        await wait_for(lambda: cohort.step_no > frozen)
        await sched.stop()

    async def test_dry_run_toggle_applies_at_cycle_boundary(self) -> None:
        cohort = make_cohort()
        results: list[CycleResult] = []
        sched = CycleScheduler(cohort, interval_seconds=0.02, on_result=results.append)
        sched.set_dry_run(True)
        sched.start()
        await wait_for(lambda: len(results) >= 2)
        await sched.stop()
        assert all(r.dry_run for r in results)

    async def test_start_is_idempotent(self) -> None:
        cohort = make_cohort()
        sched = CycleScheduler(cohort, interval_seconds=0.02)
        sched.start()
        sched.start()  # 二重起動しても単一ループ
        await wait_for(lambda: cohort.step_no >= 2)
        await sched.stop()
        # 二重起動なら同一step_noのサイクルが重複するはずだが、単調増加のみ
        assert cohort.step_no == len(cohort.tv_history)
