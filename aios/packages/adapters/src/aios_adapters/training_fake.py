"""決定的な FakeTrainer(学習系 Rehatch のテスト基盤)。

実 GPU 学習を持たない環境で、非同期ジョブのライフサイクル(投入→進捗→完了/失敗)を
決定的に再現する。poll するたびにステップが1つ前進し、max_steps 到達で SUCCEEDED、
その際 result_config に「教師ベクトルを制御ベクトルに採用した新構成」を返す
(適用すると get_state≈TV となりスモーク検証を通過する)。

失敗注入(fail_at_step)で FAILED 経路も検証できる。実運用ではこの Protocol を
満たす本番トレーナー(蒸留・LoRA 等)に差し替える。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from aios_adapters.spi import (
    TrainingJobState,
    TrainingRequest,
    TrainingStatus,
)

_BASE_SCORE = 0.3


@dataclass
class _Job:
    request: TrainingRequest
    step: int = 0
    status: TrainingStatus = TrainingStatus.PENDING
    fail_at_step: int | None = None


class FakeTrainer:
    """インメモリのジョブ台帳を持つ決定的トレーナー。"""

    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._counter = 0
        # slot_id -> 次ジョブで注入する失敗ステップ(テストフック)
        self._fail_injections: dict[str, int] = {}

    def inject_failure(self, slot_id: str, at_step: int) -> None:
        """次にその slot で submit されたジョブを at_step で失敗させる。"""
        self._fail_injections[slot_id] = at_step

    def submit(self, request: TrainingRequest) -> str:
        self._counter += 1
        job_id = f"job-{self._counter}"
        self._jobs[job_id] = _Job(
            request=request,
            fail_at_step=self._fail_injections.pop(request.slot_id, None),
        )
        return job_id

    def poll(self, job_id: str) -> TrainingJobState:
        job = self._jobs[job_id]
        if job.status in (TrainingStatus.SUCCEEDED, TrainingStatus.FAILED):
            return self._state(job, job_id)

        job.step += 1
        if job.fail_at_step is not None and job.step >= job.fail_at_step:
            job.status = TrainingStatus.FAILED
        elif job.step >= job.request.max_steps:
            job.status = TrainingStatus.SUCCEEDED
        else:
            job.status = TrainingStatus.RUNNING
        return self._state(job, job_id)

    def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is not None and job.status in (TrainingStatus.PENDING, TrainingStatus.RUNNING):
            job.status = TrainingStatus.FAILED
            job.fail_at_step = job.step  # cancelled

    def _state(self, job: _Job, job_id: str) -> TrainingJobState:
        req = job.request
        progress = min(1.0, job.step / max(1, req.max_steps))
        score = _BASE_SCORE + (req.target_fitness - _BASE_SCORE) * progress

        if job.status is TrainingStatus.FAILED:
            return TrainingJobState(job_id, job.status, progress, job.step, "training failed")
        if job.status is TrainingStatus.SUCCEEDED:
            trained = replace(
                req.base_config,
                context_vector=req.teacher_vector,
                params_uri=f"fake-trained://{req.slot_id}/{job_id}",
            )
            return TrainingJobState(
                job_id, job.status, 1.0, job.step, "converged",
                result_config=trained, score=req.target_fitness,
            )
        # RUNNING/PENDING: 進捗に応じた見込みスコアも返す(可視化用)
        return TrainingJobState(
            job_id, job.status, progress, job.step, f"step {job.step}", score=round(score, 4)
        )
