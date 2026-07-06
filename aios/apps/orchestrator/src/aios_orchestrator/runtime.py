"""コホートランタイム(P1: インメモリ)と卵層(Hatchery)。

- hatch_cohort は初期化フェーズ(Phase1)専用。OPERATING遷移後の再実行は
  PhaseLockedError(卵層の非再入、請求項10)
- SlotRuntime は Adapter実体 + 投影(SlotView相当) + イベントチェーンを束ねる。
  P2でpackages/storageの永続実装に置換するが、境界(このモジュールの公開型)は維持する
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
from aios_adapters.spi import ModelAdapter, Vector
from aios_common.errors import PhaseLockedError
from aios_core.lineage.events import EventChainBuilder, SlotEvent, SlotEventType
from aios_core.policy.health import HealthJudge
from aios_core.policy.safety import NegativeCentroid
from aios_core.types import (
    CohortPhase,
    DynamicsSignal,
    HealthStatus,
    HealthThresholds,
    SlotStatus,
    SlotView,
)


@dataclass
class SlotRuntime:
    slot_id: str
    display_id: str
    adapter: ModelAdapter
    chain: EventChainBuilder
    events: list[SlotEvent] = field(default_factory=list)
    status: SlotStatus = SlotStatus.ACTIVE
    generation: int = 0
    maturity: int = 0
    fitness_hat: float | None = None
    rehatch_lock: bool = False
    last_rehatch_at: datetime | None = None
    assign_share: float = 0.0

    def record(
        self, event_type: SlotEventType, payload: dict, occurred_at: datetime
    ) -> SlotEvent:
        ev = self.chain.append(event_type, self.generation, payload, occurred_at)
        self.events.append(ev)
        return ev

    def view(self) -> SlotView:
        return SlotView(
            slot_id=self.slot_id,
            display_id=self.display_id,
            status=self.status,
            generation=self.generation,
            maturity=self.maturity,
            fitness_hat=self.fitness_hat,
            rehatch_lock=self.rehatch_lock,
            last_rehatch_at=self.last_rehatch_at,
            assign_share=self.assign_share,
        )


@dataclass
class CohortRuntime:
    cohort_id: str
    phase: CohortPhase
    slots: list[SlotRuntime]
    teacher_vector: Vector
    thresholds: HealthThresholds
    ema_alpha: float = 0.1
    dynamics: DynamicsSignal = field(default_factory=DynamicsSignal)
    judge: HealthJudge = field(default_factory=HealthJudge)
    step_no: int = 0
    tv_history: list[Vector] = field(default_factory=list)
    # 安全境界(FR-SF): 禁止ベクトルのレジストリ
    negative_centroids: list[NegativeCentroid] = field(default_factory=list)
    # 次元拡張(FR-SC): 拡張次元の価値軸レジストリ(dim_index -> label)
    value_axes: dict[int, str] = field(default_factory=dict)
    # 成熟点検出(FR-LC-04)用の時系列
    drift_history: list[float] = field(default_factory=list)
    health_history: list[HealthStatus] = field(default_factory=list)
    fitness_mean_history: list[float] = field(default_factory=list)


def hatch_cohort(
    *,
    adapter_factory,  # (index: int, seed_vector: Vector) -> ModelAdapter
    slot_count: int,
    initial_tv: Vector,
    thresholds: HealthThresholds,
    diversity: float = 0.3,
    seed: int = 0,
    ema_alpha: float = 0.1,
    now: datetime | None = None,
) -> CohortRuntime:
    """卵層(Egg Layer): 初期教師ベクトルT_0とシードに基づきK体を生成する(Phase1)。

    生成完了時に OPERATING へ遷移し、以降この関数を同一コホートに再適用する経路はない
    (再入はrehatch_guardが拒否する。請求項10)。
    """
    if slot_count < 2:
        raise ValueError("slot_count must be >= 2")
    now = now or datetime.now(UTC)
    rng = np.random.default_rng(seed)
    t0 = np.asarray(initial_tv, dtype=np.float64)
    t0 = t0 / np.linalg.norm(t0)

    slots: list[SlotRuntime] = []
    for i in range(slot_count):
        # T_0の周囲に初期多様性diversityで分布させる(¶0100)
        seed_vec = t0 + rng.normal(scale=diversity, size=t0.shape)
        seed_vec = seed_vec / np.linalg.norm(seed_vec)
        slot_id = str(uuid.uuid4())
        rt = SlotRuntime(
            slot_id=slot_id,
            display_id=f"{i + 1:03d}",
            adapter=adapter_factory(i, seed_vec),
            chain=EventChainBuilder(slot_id=slot_id),
        )
        rt.record(SlotEventType.SLOT_CREATED, {"seed_index": i, "diversity": diversity}, now)
        slots.append(rt)

    return CohortRuntime(
        cohort_id=str(uuid.uuid4()),
        phase=CohortPhase.OPERATING,
        slots=slots,
        teacher_vector=t0,
        thresholds=thresholds,
        ema_alpha=ema_alpha,
    )


def guard_hatchery(cohort: CohortRuntime) -> None:
    """卵層の非再入ガード(請求項10)。OPERATING中の追加生成要求を拒否する。"""
    if cohort.phase == CohortPhase.OPERATING:
        raise PhaseLockedError(
            "cohort is in OPERATING phase: slot generation is sealed (claim 10)"
        )
