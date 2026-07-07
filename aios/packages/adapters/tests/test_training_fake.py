"""FakeTrainer(学習系 Rehatch のテスト基盤)のジョブライフサイクル検証。"""

from __future__ import annotations

from aios_adapters.spi import ModelConfig, RehatchStrategy, TrainingRequest, TrainingStatus
from aios_adapters.training_fake import FakeTrainer


def _request(slot_id: str = "s1", max_steps: int = 3) -> TrainingRequest:
    return TrainingRequest(
        slot_id=slot_id,
        strategy=RehatchStrategy.DISTILLATION,
        teacher_vector=(0.0, 1.0, 0.0),
        base_config=ModelConfig(system_prompt="base"),
        max_steps=max_steps,
        target_fitness=0.9,
    )


def test_job_progresses_to_success() -> None:
    trainer = FakeTrainer()
    job_id = trainer.submit(_request(max_steps=3))

    s1 = trainer.poll(job_id)
    assert s1.status is TrainingStatus.RUNNING and s1.step == 1
    s2 = trainer.poll(job_id)
    assert 0.0 < s1.progress < s2.progress  # 進捗は単調増加
    s3 = trainer.poll(job_id)
    assert s3.status is TrainingStatus.SUCCEEDED
    assert s3.progress == 1.0 and s3.score == 0.9
    # 完了構成: 教師ベクトルを制御ベクトルに採用し、重み参照を持つ
    assert s3.result_config is not None
    assert s3.result_config.context_vector == (0.0, 1.0, 0.0)
    assert s3.result_config.params_uri is not None
    # ベース構成を引き継ぐ
    assert s3.result_config.system_prompt == "base"


def test_terminal_state_is_idempotent() -> None:
    trainer = FakeTrainer()
    job_id = trainer.submit(_request(max_steps=1))
    done = trainer.poll(job_id)
    assert done.status is TrainingStatus.SUCCEEDED
    again = trainer.poll(job_id)
    assert again.status is TrainingStatus.SUCCEEDED and again.step == done.step


def test_failure_injection() -> None:
    trainer = FakeTrainer()
    trainer.inject_failure("s1", at_step=2)
    job_id = trainer.submit(_request(slot_id="s1", max_steps=5))
    assert trainer.poll(job_id).status is TrainingStatus.RUNNING
    failed = trainer.poll(job_id)
    assert failed.status is TrainingStatus.FAILED
    assert failed.result_config is None


def test_cancel() -> None:
    trainer = FakeTrainer()
    job_id = trainer.submit(_request(max_steps=10))
    trainer.poll(job_id)
    trainer.cancel(job_id)
    assert trainer.poll(job_id).status is TrainingStatus.FAILED


def test_distinct_job_ids() -> None:
    trainer = FakeTrainer()
    a = trainer.submit(_request())
    b = trainer.submit(_request())
    assert a != b
