"""CycleScheduler — 制御ループの周期駆動(FR-LC-03 / docs/03 §3.1)。

コホートごとに1つのスケジューラが run_cycle を周期実行する。
pause/resume/dry-run はサイクル境界で反映され、実行中サイクルは中断しない
(グレースフル、NFR-OP-02)。停止時は実行中サイクルの完了を待つ。

P2以降: 複数レプリカ構成では分散ロック(Redis)で単一実行を保証する。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from enum import StrEnum

from aios_orchestrator.cycle import CycleConfig, CycleResult, run_cycle
from aios_orchestrator.runtime import CohortRuntime


class LoopState(StrEnum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class CycleScheduler:
    def __init__(
        self,
        cohort: CohortRuntime,
        *,
        interval_seconds: float,
        cfg: CycleConfig | None = None,
        on_result: Callable[[CycleResult], None] | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._cohort = cohort
        self._interval = interval_seconds
        self._cfg = cfg or CycleConfig()
        self._on_result = on_result
        self._state = LoopState.STOPPED
        self._dry_run = self._cfg.dry_run
        self._task: asyncio.Task[None] | None = None
        self._wakeup = asyncio.Event()

    @property
    def state(self) -> LoopState:
        return self._state

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return  # 冪等
        self._state = LoopState.RUNNING
        self._task = asyncio.create_task(self._loop(), name=f"aios-cycle-{self._cohort.cohort_id}")

    def pause(self) -> None:
        if self._state == LoopState.RUNNING:
            self._state = LoopState.PAUSED

    def resume(self) -> None:
        if self._state == LoopState.PAUSED:
            self._state = LoopState.RUNNING
            self._wakeup.set()

    def set_dry_run(self, enabled: bool) -> None:
        self._dry_run = enabled

    async def stop(self) -> None:
        """実行中サイクルの完了を待って停止する(グレースフル)。"""
        self._state = LoopState.STOPPED
        self._wakeup.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _sleep(self) -> None:
        """interval待機。resume/stopで即時起床する。"""
        self._wakeup.clear()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wakeup.wait(), timeout=self._interval)

    async def _loop(self) -> None:
        while self._state != LoopState.STOPPED:
            if self._state == LoopState.RUNNING:
                from dataclasses import replace

                cfg = replace(self._cfg, dry_run=self._dry_run)
                result = await run_cycle(self._cohort, cfg)
                if self._on_result is not None:
                    self._on_result(result)
            await self._sleep()
