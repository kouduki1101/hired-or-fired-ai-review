"""コホートの永続化とrehydrate(ADR-001の実証 / NFR-AV-03)。

- save_cohort: 未保存イベントの差分追記(ハッシュチェーン検証付き)、
  構成スナップショットのupsert、投影(SlotRow)と教師ベクトルの保存
- load_cohort: DBからイベントを検証・リプレイして状態を復元し、
  スナップショットからAdapter実体を再構成する

これによりプロセス再起動後も、slot_id・運用履歴・世代・教師ベクトルが
断絶なく引き継がれる(請求項1の永続性保証)。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
from aios_adapters.spi import ModelAdapter, ModelConfig
from aios_core.lineage.events import GENESIS_HASH, EventChainBuilder
from aios_core.lineage.replay import replay_slot
from aios_core.types import CohortPhase, DynamicsSignal, HealthThresholds, SlotStatus
from aios_storage.event_store import EventStore
from aios_storage.models import CohortRow, ModelSnapshotRow, SlotRow, TeacherVectorRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aios_orchestrator.runtime import CohortRuntime, SlotRuntime

# ロード時のAdapter再構成: (index, 保存済みModelConfig) -> ModelAdapter
AdapterRestorer = Callable[[int, ModelConfig], ModelAdapter]


def _as_utc(dt: datetime | None) -> datetime | None:
    """tz情報を持たない方言(SQLite)からの読み出しをUTC awareへ正規化する。"""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _config_to_json(config: ModelConfig) -> dict:
    d = asdict(config)
    if d.get("context_vector") is not None:
        d["context_vector"] = list(d["context_vector"])
    return d


def _config_from_json(d: dict) -> ModelConfig:
    if d.get("context_vector") is not None:
        d = {**d, "context_vector": tuple(float(x) for x in d["context_vector"])}
    return ModelConfig(**d)


async def save_cohort(
    session: AsyncSession,
    cohort: CohortRuntime,
    *,
    tenant_id: str = "default",
    display_name: str | None = None,
) -> None:
    """冪等な保存。イベントはチェーンの続きだけを追記する。"""
    now = datetime.now(UTC)

    row = await session.get(CohortRow, cohort.cohort_id)
    runtime_state = {
        "step_no": cohort.step_no,
        "dynamics": {
            "lr_correction": cohort.dynamics.lr_correction,
            "noise_amount": cohort.dynamics.noise_amount,
        },
        "thresholds": {
            "lower": cohort.thresholds.lower,
            "upper": cohort.thresholds.upper,
            "hysteresis_cycles": cohort.thresholds.hysteresis_cycles,
        },
    }
    if row is None:
        row = CohortRow(
            cohort_id=cohort.cohort_id,
            tenant_id=tenant_id,
            name=display_name or cohort.cohort_id,
            phase=str(cohort.phase),
            slot_count=len(cohort.slots),
            tv_dimension=int(cohort.teacher_vector.shape[0]),
            ema_alpha=cohort.ema_alpha,
            config=runtime_state,
            created_at=now,
        )
        session.add(row)
    else:
        row.phase = str(cohort.phase)
        row.tv_dimension = int(cohort.teacher_vector.shape[0])
        row.config = runtime_state
        if display_name is not None:
            row.name = display_name

    # 教師ベクトル(第1の指標)の最新値を追記(履歴は追記のみ、docs/04 不変条件6)
    session.add(
        TeacherVectorRow(
            tv_id=str(uuid.uuid4()),
            cohort_id=cohort.cohort_id,
            dimension=int(cohort.teacher_vector.shape[0]),
            vector=[float(x) for x in cohort.teacher_vector],
            source="ema_update",
            measured_at=now,
        )
    )

    store = EventStore(session, tenant_id=tenant_id)
    for slot in cohort.slots:
        slot_row = await session.get(SlotRow, slot.slot_id)
        if slot_row is None:
            slot_row = SlotRow(
                slot_id=slot.slot_id,
                tenant_id=tenant_id,
                cohort_id=cohort.cohort_id,
                display_id=slot.display_id,
                adapter_kind=slot.adapter.capabilities().adapter_kind,
            )
            session.add(slot_row)
        slot_row.generation = slot.generation
        slot_row.status = str(slot.status)
        slot_row.maturity = slot.maturity
        slot_row.fitness = slot.fitness_hat
        slot_row.rehatch_lock = slot.rehatch_lock
        slot_row.last_rehatch_at = slot.last_rehatch_at

        # イベント差分追記: DBの末尾hashに一致する位置から先を書く
        last_hash = await store.last_hash(slot.slot_id)
        start = 0
        if last_hash != GENESIS_HASH:
            start = next(
                (i + 1 for i, ev in enumerate(slot.events) if ev.hash == last_hash), None
            ) or _raise_diverged(slot.slot_id)
        for ev in slot.events[start:]:
            await store.append(ev, cohort_id=cohort.cohort_id)

        # 現行世代の構成スナップショット(ロールバック・rehydrate用)をupsert
        existing = await session.scalar(
            select(ModelSnapshotRow).where(
                ModelSnapshotRow.slot_id == slot.slot_id,
                ModelSnapshotRow.generation == slot.generation,
            )
        )
        config = await slot.adapter.snapshot()
        if existing is None:
            session.add(
                ModelSnapshotRow(
                    snapshot_id=str(uuid.uuid4()),
                    slot_id=slot.slot_id,
                    generation=slot.generation,
                    adapter_kind=slot.adapter.capabilities().adapter_kind,
                    config=_config_to_json(config),
                    created_by="save",
                    created_at=now,
                )
            )
        else:
            existing.config = _config_to_json(config)

    await session.flush()


def _raise_diverged(slot_id: str) -> int:
    raise ValueError(
        f"slot {slot_id}: in-memory event chain does not continue the persisted chain"
    )


async def load_cohort(
    session: AsyncSession,
    cohort_id: str,
    adapter_restorer: AdapterRestorer,
    *,
    tenant_id: str = "default",
) -> CohortRuntime:
    """イベント検証+リプレイ+スナップショット適用で完全復元する。"""
    row = await session.get(CohortRow, cohort_id)
    if row is None:
        raise LookupError(f"cohort {cohort_id} not found")

    tv_row = await session.scalar(
        select(TeacherVectorRow)
        .where(TeacherVectorRow.cohort_id == cohort_id)
        .order_by(TeacherVectorRow.measured_at.desc(), TeacherVectorRow.tv_id.desc())
        .limit(1)
    )
    if tv_row is None:
        raise LookupError(f"cohort {cohort_id} has no teacher vector")

    state = row.config or {}
    thresholds = HealthThresholds(**state["thresholds"])
    store = EventStore(session, tenant_id=tenant_id)

    slot_rows = (
        await session.scalars(
            select(SlotRow).where(SlotRow.cohort_id == cohort_id).order_by(SlotRow.display_id)
        )
    ).all()

    slots: list[SlotRuntime] = []
    for i, sr in enumerate(slot_rows):
        events = await store.list_for_slot(sr.slot_id)  # verify込みでリプレイ
        replayed = replay_slot(events)
        if replayed.generation != sr.generation:
            raise ValueError(
                f"slot {sr.slot_id}: projection generation {sr.generation} "
                f"!= replayed {replayed.generation}"
            )

        snap_row = await session.scalar(
            select(ModelSnapshotRow).where(
                ModelSnapshotRow.slot_id == sr.slot_id,
                ModelSnapshotRow.generation == sr.generation,
            )
        )
        if snap_row is None:
            raise LookupError(f"slot {sr.slot_id}: snapshot for gen {sr.generation} missing")
        config = _config_from_json(dict(snap_row.config))

        adapter = adapter_restorer(i, config)
        await adapter.apply_params(config)

        slots.append(
            SlotRuntime(
                slot_id=sr.slot_id,
                display_id=sr.display_id,
                adapter=adapter,
                chain=EventChainBuilder(slot_id=sr.slot_id, last_hash=events[-1].hash),
                events=events,
                status=SlotStatus(sr.status),
                generation=sr.generation,
                maturity=sr.maturity,
                fitness_hat=sr.fitness,
                rehatch_lock=sr.rehatch_lock,
                last_rehatch_at=_as_utc(sr.last_rehatch_at),
            )
        )

    cohort = CohortRuntime(
        cohort_id=cohort_id,
        phase=CohortPhase(row.phase),
        slots=slots,
        teacher_vector=np.asarray(tv_row.vector, dtype=np.float64),
        thresholds=thresholds,
        ema_alpha=row.ema_alpha,
        dynamics=DynamicsSignal(**state.get("dynamics", {})),
        step_no=int(state.get("step_no", 0)),
    )
    return cohort
