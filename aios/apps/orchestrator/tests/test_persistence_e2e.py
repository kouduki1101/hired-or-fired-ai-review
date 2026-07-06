"""永続化ラウンドトリップe2e(ADR-001 / NFR-AV-03)。

シナリオ: 卵層→サイクル数回→逸脱スロットのRehatch(世代+1)→保存
→「プロセス再起動」を模して別ランタイムへロード→状態完全一致→運用継続可能。
"""

from __future__ import annotations

import numpy as np
import pytest
from aios_adapters.fake import FakeAgentAdapter
from aios_adapters.spi import ModelConfig
from aios_core.types import HealthThresholds, RehatchSelectConfig
from aios_orchestrator.cycle import CycleConfig, run_cycle
from aios_orchestrator.persistence import load_cohort, save_cohort
from aios_orchestrator.runtime import CohortRuntime, hatch_cohort
from aios_storage.models import SlotEventRow
from aios_storage.schema import create_all
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DIM = 8
TH = HealthThresholds(lower=0.05, upper=1.2, hysteresis_cycles=2)
CFG = CycleConfig(rehatch=RehatchSelectConfig(cooldown_seconds=0))


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


def restore_adapter(index: int, config: ModelConfig) -> FakeAgentAdapter:
    """スナップショットのcontext_vector(挙動)からFakeAdapterを再構成。"""
    assert config.context_vector is not None
    return FakeAgentAdapter(behavior=np.asarray(config.context_vector), seed=1000 + index)


async def build_operated_cohort() -> CohortRuntime:
    """運用済み(Rehatch含む)のコホートを作る。"""
    rng = np.random.default_rng(21)
    cohort = hatch_cohort(
        adapter_factory=lambda i, seed_vec: FakeAgentAdapter(behavior=seed_vec, seed=1000 + i),
        slot_count=6,
        initial_tv=rng.normal(size=DIM),
        thresholds=TH,
        seed=9,
    )
    await run_cycle(cohort, CFG)
    cohort.slots[1].adapter.force_behavior(-cohort.teacher_vector)  # type: ignore[attr-defined]
    for _ in range(5):
        await run_cycle(cohort, CFG)
    assert cohort.slots[1].generation >= 1, "前提: Rehatchが発生していること"
    return cohort


class TestRoundtrip:
    async def test_full_state_survives_restart(self, session: AsyncSession) -> None:
        original = await build_operated_cohort()
        await save_cohort(session, original)

        # 「再起動」: 新しいランタイムをDBから復元
        restored = await load_cohort(session, original.cohort_id, restore_adapter)

        assert restored.step_no == original.step_no
        assert restored.phase == original.phase
        assert restored.teacher_vector == pytest.approx(original.teacher_vector)
        assert restored.dynamics == original.dynamics
        assert restored.thresholds == original.thresholds

        for orig, rest in zip(original.slots, restored.slots, strict=True):
            # 請求項1の核: slot_id・世代・運用履歴が再起動を跨いで連続
            assert rest.slot_id == orig.slot_id
            assert rest.display_id == orig.display_id
            assert rest.generation == orig.generation
            assert rest.maturity == orig.maturity
            assert rest.fitness_hat == pytest.approx(orig.fitness_hat)
            assert len(rest.events) == len(orig.events)
            assert rest.events[-1].hash == orig.events[-1].hash

        # Adapter実体の構成(広義の内部パラメータ)が復元されている
        # ※get_stateはノイズ揺らぎを含むため、決定的なsnapshot()で比較する
        for orig, rest in zip(original.slots, restored.slots, strict=True):
            o = await orig.adapter.snapshot()
            r = await rest.adapter.snapshot()
            assert r.context_vector == pytest.approx(o.context_vector)

    async def test_operation_continues_after_restore(self, session: AsyncSession) -> None:
        """復元後もイベントチェーンの続きとして運用できる(履歴の断絶なし)。"""
        original = await build_operated_cohort()
        await save_cohort(session, original)
        restored = await load_cohort(session, original.cohort_id, restore_adapter)

        before_steps = restored.step_no
        result = await run_cycle(restored, CFG)
        assert result.step_no == before_steps + 1

        # 継続分のイベントも保存でき、チェーンが繋がる(差分追記)
        await save_cohort(session, restored)
        reloaded = await load_cohort(session, restored.cohort_id, restore_adapter)
        assert reloaded.step_no == restored.step_no
        for slot in reloaded.slots:
            assert slot.events[0].event_type.value == "SLOT_CREATED"

    async def test_save_is_idempotent(self, session: AsyncSession) -> None:
        """同一状態の二重保存でイベントが重複しない。"""
        cohort = await build_operated_cohort()
        await save_cohort(session, cohort)
        count1 = len((await session.scalars(SlotEventRow.__table__.select())).all())
        await save_cohort(session, cohort)
        count2 = len((await session.scalars(SlotEventRow.__table__.select())).all())
        assert count1 == count2

    async def test_load_missing_cohort_raises(self, session: AsyncSession) -> None:
        with pytest.raises(LookupError):
            await load_cohort(session, "no-such-cohort", restore_adapter)
