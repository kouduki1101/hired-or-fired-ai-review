"""Autopilot — 制御ループの常駐駆動(FR-LC-03 / 長期運用基盤の自動運転)。

コホートごとに asyncio タスクを1本持ち、interval ごとに cycle_service.execute_cycle
を実行する。手動実行と完全に同じ後処理(承認・課金・Webhook・永続化・計測)を通る。

- PAUSED のコホートはサイクルをスキップ(ループ状態はサイクル境界で反映)
- 一過性エラーでは常駐を止めず、構造化ログに記録して次周期へ(長期運用の生存性)
- stop はグレースフル: 実行中サイクルの完了を待つ(NFR-OP-02)
- 有効化: 環境変数 AIOS_AUTOPILOT_INTERVAL_SECONDS(起動時に全コホート自動開始)
  または POST /v1/cohorts/{id}/loop の autopilot_on / autopilot_off

複数レプリカ構成ではコホート状態と同様にプロセス内(担当レプリカに集約する前提)。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from aios_api.logging_config import log_event


def env_interval() -> float | None:
    raw = os.environ.get("AIOS_AUTOPILOT_INTERVAL_SECONDS")
    if not raw:
        return None
    value = float(raw)
    return value if value > 0 else None


class Autopilot:
    """コホートID -> 常駐タスクの管理。単一イベントループ内で使用する。"""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._stops: dict[str, asyncio.Event] = {}
        self._intervals: dict[str, float] = {}

    def is_running(self, cohort_id: str) -> bool:
        task = self._tasks.get(cohort_id)
        return task is not None and not task.done()

    def interval_of(self, cohort_id: str) -> float | None:
        return self._intervals.get(cohort_id) if self.is_running(cohort_id) else None

    def start(self, cohort_id: str, interval_seconds: float) -> None:
        """開始(既に走っていれば interval を変えて張り直す)。"""
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if self.is_running(cohort_id):
            # 既存ループは止めずに interval のみ更新(次の待機から反映)
            self._intervals[cohort_id] = interval_seconds
            return
        stop = asyncio.Event()
        self._stops[cohort_id] = stop
        self._intervals[cohort_id] = interval_seconds
        self._tasks[cohort_id] = asyncio.create_task(
            self._loop(cohort_id, stop), name=f"aios-autopilot-{cohort_id}"
        )
        log_event("autopilot.started", cohort_id=cohort_id, interval_seconds=interval_seconds)

    async def stop(self, cohort_id: str) -> None:
        """グレースフル停止(実行中サイクルの完了を待つ)。"""
        task = self._tasks.pop(cohort_id, None)
        stop = self._stops.pop(cohort_id, None)
        if stop is not None:
            stop.set()
        if task is not None:
            await task
            log_event("autopilot.stopped", cohort_id=cohort_id)
        # interval はループが参照するため、タスク完了後に破棄する
        self._intervals.pop(cohort_id, None)

    async def stop_all(self) -> None:
        for cohort_id in list(self._tasks):
            await self.stop(cohort_id)

    async def _loop(self, cohort_id: str, stop: asyncio.Event) -> None:
        from aios_api.auth import current_tenant
        from aios_api.cycle_service import execute_cycle
        from aios_api.store import STORE

        while not stop.is_set():
            if STORE.loop_state(cohort_id) != "PAUSED":
                try:
                    # バックグラウンドタスクにはリクエストのテナント文脈がないため、
                    # コホートの所属テナントを設定する(get_cohort検査・Webhook配送先の解決)
                    token = current_tenant.set(STORE.tenant_of(cohort_id))
                    try:
                        await execute_cycle(cohort_id)
                    finally:
                        current_tenant.reset(token)
                except Exception as exc:  # 常駐は一過性エラーで死なない
                    log_event(
                        "autopilot.cycle_error",
                        level=logging.ERROR,
                        cohort_id=cohort_id,
                        error=f"{type(exc).__name__}: {exc}",
                    )
            with contextlib.suppress(TimeoutError):
                # stop() 直後の競合に備え、消えていたら短い待機で終端へ向かう
                await asyncio.wait_for(
                    stop.wait(), timeout=self._intervals.get(cohort_id, 0.05)
                )


AUTOPILOT = Autopilot()
