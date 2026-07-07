"""学習系 Rehatch の非同期ジョブ調停(docs/06 §7 手法B/C, 明細書 ¶0057)。

TV-Init(手法A、cycle._execute_rehatch)が同期・即時なのに対し、蒸留・アダプタ再生成は
時間を要する非同期ジョブとして実行される。本モジュールはジョブの投入・進捗監視と、
完了時の Rehatch-in-Place(slot_id・履歴維持のまま世代+1)への写像を担う。

- 学習はシャドウで進み、スロットは学習中もタスクを処理し続ける(オフラインにしない)。
- 完了時に新構成を適用し、スモーク検証(適合度下限)に通れば確定、落ちればロールバック。
  この確定/ロールバックの規則は同期 Rehatch と同一(一貫した監査像)。
"""

from __future__ import annotations

from datetime import datetime

from aios_adapters.spi import (
    RehatchStrategy,
    Trainer,
    TrainingJobState,
    TrainingRequest,
    TrainingStatus,
    Vector,
)
from aios_core.lineage.events import SlotEventType
from aios_core.metrics import fitness_score
from aios_core.metrics.maturity import reset_maturity
from aios_core.types import SlotStatus

from aios_orchestrator.cycle import RehatchOutcome
from aios_orchestrator.runtime import SlotRuntime


class TrainingCoordinator:
    """Trainer(データプレーン)を包み、学習系 Rehatch を制御プレーンへ橋渡しする。"""

    def __init__(self, trainer: Trainer) -> None:
        self._trainer = trainer
        self._active: dict[str, str] = {}  # slot_id -> job_id
        self._strategy: dict[str, RehatchStrategy] = {}  # job_id -> strategy

    def active_job(self, slot_id: str) -> str | None:
        return self._active.get(slot_id)

    async def submit(
        self,
        slot: SlotRuntime,
        strategy: RehatchStrategy,
        teacher_vector: Vector,
        now: datetime,
        *,
        max_steps: int = 10,
        target_fitness: float = 0.9,
    ) -> str:
        """学習ジョブを投入する。スロットは ACTIVE のまま(シャドウ学習)。"""
        base = await slot.adapter.snapshot()
        request = TrainingRequest(
            slot_id=slot.slot_id,
            strategy=strategy,
            teacher_vector=tuple(float(x) for x in teacher_vector),
            base_config=base,
            max_steps=max_steps,
            target_fitness=target_fitness,
        )
        job_id = self._trainer.submit(request)
        self._active[slot.slot_id] = job_id
        self._strategy[job_id] = strategy
        slot.record(
            SlotEventType.REHATCH_STARTED,
            {"strategy": str(strategy), "mode": "async", "job_id": job_id},
            now,
        )
        return job_id

    def poll(self, job_id: str) -> TrainingJobState:
        return self._trainer.poll(job_id)

    async def apply_if_ready(
        self,
        slot: SlotRuntime,
        job_id: str,
        teacher_vector: Vector,
        now: datetime,
        *,
        smoke_floor: float = 0.5,
    ) -> RehatchOutcome | None:
        """ジョブを進め、完了していれば Rehatch-in-Place を実施する。

        未完了なら None。FAILED または スモーク不合格なら committed=False。
        """
        state = self._trainer.poll(job_id)
        strategy = self._strategy.get(job_id, RehatchStrategy.DISTILLATION)
        slot.record(
            SlotEventType.TRAINING_STEP,
            {
                "job_id": job_id,
                "status": str(state.status),
                "progress": round(state.progress, 4),
                "step": state.step,
            },
            now,
        )

        if state.status in (TrainingStatus.PENDING, TrainingStatus.RUNNING):
            return None

        if state.status is TrainingStatus.FAILED:
            self._clear(slot.slot_id, job_id)
            slot.record(
                SlotEventType.REHATCH_ROLLED_BACK,
                {"strategy": str(strategy), "reason": "training_failed", "job_id": job_id},
                now,
            )
            return RehatchOutcome(slot.slot_id, "training_failed", False, slot.generation)

        # SUCCEEDED → Rehatch-in-Place(世代+1)。落ちたらロールバック。
        assert state.result_config is not None
        rollback_config = await slot.adapter.snapshot()
        slot.status = SlotStatus.REHATCHING
        await slot.adapter.apply_params(state.result_config)
        new_state = await slot.adapter.get_state([])
        smoke_fitness = fitness_score(new_state, teacher_vector)

        if smoke_fitness >= smoke_floor:
            slot.generation += 1
            slot.maturity = reset_maturity()
            slot.fitness_hat = smoke_fitness
            slot.last_rehatch_at = now
            slot.status = SlotStatus.ACTIVE
            self._clear(slot.slot_id, job_id)
            slot.record(
                SlotEventType.REHATCH_COMPLETED,
                {
                    "strategy": str(strategy),
                    "reason": "learning",
                    "job_id": job_id,
                    "smoke_fitness": round(smoke_fitness, 6),
                    "trained_score": state.score,
                    "maturity_after": 0,
                },
                now,
            )
            return RehatchOutcome(slot.slot_id, "learning", True, slot.generation)

        await slot.adapter.apply_params(rollback_config)
        slot.status = SlotStatus.ACTIVE
        self._clear(slot.slot_id, job_id)
        slot.record(
            SlotEventType.REHATCH_ROLLED_BACK,
            {
                "strategy": str(strategy),
                "reason": "smoke_failed",
                "job_id": job_id,
                "smoke_fitness": round(smoke_fitness, 6),
            },
            now,
        )
        return RehatchOutcome(slot.slot_id, "learning", False, slot.generation)

    def _clear(self, slot_id: str, job_id: str) -> None:
        if self._active.get(slot_id) == job_id:
            self._active.pop(slot_id, None)
        self._strategy.pop(job_id, None)
