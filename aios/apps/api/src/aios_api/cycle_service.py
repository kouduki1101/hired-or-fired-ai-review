"""制御サイクル実行サービス(FR-LC-03)。

手動実行(POST /cycles/run)と常駐駆動(autopilot)の両方が本関数を通ることで、
承認キュー・使用量計上・Webhook通知・永続化・計測の挙動を完全に一致させる。
"""

from __future__ import annotations

import time

from aios_orchestrator.cycle import CycleConfig, CycleResult, run_cycle

from aios_api.logging_config import log_event
from aios_api.store import STORE
from aios_api.telemetry import cycle_duration_ms, cycles_run, rehatches_committed, tracer


async def execute_cycle(cohort_id: str, *, dry_run: bool = False) -> CycleResult:
    """1サイクル実行+後処理一式。呼び出し側でループ状態(PAUSED)を判断すること。"""
    cohort = STORE.get_cohort(cohort_id)
    loop_state = STORE.loop_state(cohort_id)
    effective_dry_run = dry_run or loop_state == "DRY_RUN"
    previous = STORE.last_cycle(cohort_id)
    defer = cohort.approval_mode == "manual"  # 承認モード(FR-GV-05)

    with tracer.start_as_current_span("aios.cycle.run") as span:
        span.set_attribute("aios.cohort_id", cohort_id)
        span.set_attribute("aios.dry_run", effective_dry_run)
        t0 = time.perf_counter()
        result = await run_cycle(
            cohort, CycleConfig(dry_run=effective_dry_run, defer_rehatch=defer)
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        span.set_attribute("aios.step_no", result.step_no)
        span.set_attribute("aios.health", str(result.health))
        span.set_attribute("aios.rehatch_count", len(result.rehatched))

    committed = sum(1 for o in result.rehatched if o.committed)
    # メトリクス(低カーディナリティ属性=health/dry_run のみ)
    attrs = {"health": str(result.health), "dry_run": effective_dry_run}
    cycles_run.add(1, attrs)
    cycle_duration_ms.record(elapsed_ms, attrs)
    if committed:
        rehatches_committed.add(committed)
    log_event(
        "cycle.completed",
        cohort_id=cohort_id,
        step_no=result.step_no,
        health=str(result.health),
        dissipation=None if result.dissipation != result.dissipation else result.dissipation,
        rehatch_committed=committed,
        dry_run=effective_dry_run,
        duration_ms=round(elapsed_ms, 2),
    )

    STORE.set_last_cycle(cohort_id, result)
    for p_r in result.pending_rehatch:
        STORE.add_approval(
            cohort_id=cohort_id,
            action_type="rehatch",
            payload={"slot_id": p_r.slot_id, "reason": p_r.reason},
        )
    if not result.dry_run:
        STORE.bump_usage(cohort_id, "cycles_run")
        STORE.bump_usage(
            cohort_id, "probes_executed", len(cohort.slots) - result.probe_missing
        )
        STORE.bump_usage(cohort_id, "rehatches_committed", committed)
    # Webhook通知(FR-EX-01)と永続化
    await STORE.notifier.emit_from_cycle(
        cohort_id, str(previous.health) if previous else None, result
    )
    await STORE.persist(cohort_id)
    return result
