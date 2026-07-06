"""制御メインループの1サイクル(明細書 図10-12 / docs/03 §3.1)。

Snapshot → Probe(観測) → Compute(指標) → Dynamics(調整) → Select(選定)
→ Actuate(Rehatch実行+検証+ロールバック) → Persist(イベント記録)

演算・判断はすべて aios_core の純関数に委譲し、本モジュールはI/O接着に徹する(ADR-002)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
from aios_adapters.spi import ModelConfig, Vector
from aios_core.lineage.events import SlotEventType
from aios_core.metrics import (
    centroid,
    ema_update,
    fitness_score,
    output_embedding_dissipation,
    reset_maturity,
    smooth_fitness,
)
from aios_core.metrics.teacher import drift_rate
from aios_core.policy.dynamics import adjust_dynamics
from aios_core.policy.rehatch_select import RehatchSelection, select_rehatch_targets
from aios_core.policy.safety import check_danger
from aios_core.policy.stabilization import detect_stabilization_point
from aios_core.types import (
    DynamicsConfig,
    HealthStatus,
    RehatchSelectConfig,
    SlotStatus,
    StabilizationConfig,
)

from aios_orchestrator.runtime import CohortRuntime, SlotRuntime


@dataclass(frozen=True)
class CycleConfig:
    rehatch: RehatchSelectConfig = field(default_factory=RehatchSelectConfig)
    dynamics: DynamicsConfig = field(default_factory=DynamicsConfig)
    stabilization: StabilizationConfig = field(default_factory=StabilizationConfig)
    smoke_floor: float = 0.5  # Rehatch検証の合格下限
    rehatch_noise: float = 0.05  # TV-Init時のノイズ幅σ
    dry_run: bool = False  # 判断のみ記録し作用しない
    rng_seed: int = 0  # 監査リプレイ用(サイクル毎にstep_noと合成)


@dataclass(frozen=True)
class RehatchOutcome:
    slot_id: str
    reason: str
    committed: bool  # False = ロールバック
    new_generation: int


@dataclass(frozen=True)
class QuarantineOutcome:
    slot_id: str
    label: str  # 触発した禁止ベクトル
    similarity: float


@dataclass(frozen=True)
class CycleResult:
    step_no: int
    health: HealthStatus
    dissipation: float
    tv_drift: float
    fitness_mean: float
    lr_correction: float
    noise_amount: float
    rehatched: list[RehatchOutcome]
    quarantined: list[QuarantineOutcome]
    stabilization_point: bool
    probe_missing: int
    dry_run: bool


async def _observe(slot: SlotRuntime) -> Vector | None:
    """観測。Adapter障害は欠測として扱いEMAを汚さない(NFR-AV-05)。"""
    try:
        return await slot.adapter.get_state([])
    except Exception:
        return None


async def _execute_rehatch(
    slot: SlotRuntime,
    sel: RehatchSelection,
    tv: Vector,
    cfg: CycleConfig,
    rng: np.random.Generator,
    now: datetime,
) -> RehatchOutcome:
    """Rehatch-in-Place: slot_id・履歴を維持したまま内部パラメータを更新(図12)。"""
    slot.status = SlotStatus.REHATCHING
    slot.record(SlotEventType.REHATCH_STARTED, {"reason": str(sel.reason)}, now)

    rollback_config = await slot.adapter.snapshot()  # 直前世代スナップショット

    # 戦略: TV-Init(手法A) — 教師ベクトル+ノイズを制御ベクトルとして注入
    target = tv + rng.normal(scale=cfg.rehatch_noise, size=tv.shape)
    await slot.adapter.apply_params(ModelConfig(context_vector=tuple(float(x) for x in target)))

    # スモーク検証: 新状態の適合度が下限以上か
    new_state = await slot.adapter.get_state([])
    smoke_fitness = fitness_score(new_state, tv)

    if smoke_fitness >= cfg.smoke_floor:
        slot.generation += 1
        slot.maturity = reset_maturity()
        slot.fitness_hat = smoke_fitness
        slot.last_rehatch_at = now
        slot.status = SlotStatus.ACTIVE
        slot.record(
            SlotEventType.REHATCH_COMPLETED,
            {
                "strategy": "tv_init",
                "reason": str(sel.reason),
                "smoke_fitness": round(smoke_fitness, 6),
                "maturity_after": 0,
            },
            now,
        )
        return RehatchOutcome(slot.slot_id, str(sel.reason), True, slot.generation)

    # 不合格 → ロールバック(世代据え置き)
    await slot.adapter.apply_params(rollback_config)
    slot.status = SlotStatus.ACTIVE
    slot.record(
        SlotEventType.REHATCH_ROLLED_BACK,
        {"reason": str(sel.reason), "smoke_fitness": round(smoke_fitness, 6)},
        now,
    )
    return RehatchOutcome(slot.slot_id, str(sel.reason), False, slot.generation)


async def run_cycle(
    cohort: CohortRuntime,
    cfg: CycleConfig = CycleConfig(),  # noqa: B008 - frozen dataclass
    now: datetime | None = None,
) -> CycleResult:
    now = now or datetime.now(UTC)
    cohort.step_no += 1
    rng = np.random.default_rng(cfg.rng_seed + cohort.step_no)  # 決定的(リプレイ可能)

    # --- Probe: 稼働スロットの状態収集(欠測は除外) ---
    active = [s for s in cohort.slots if s.status == SlotStatus.ACTIVE]
    states: dict[str, Vector] = {}
    missing = 0
    for s in active:
        v = await _observe(s)
        if v is None:
            missing += 1
        else:
            states[s.slot_id] = v

    # --- Safety: 禁止ベクトル照合(¶0237)。危険予兆スロットは即時隔離し、
    #     当サイクルのTV計算から寄与を除外する(汚染除去、FR-SF-02/03) ---
    quarantined: list[QuarantineOutcome] = []
    if cohort.negative_centroids and not cfg.dry_run:
        for s in active:
            state = states.get(s.slot_id)
            if state is None:
                continue
            hit = check_danger(state, cohort.negative_centroids)
            if hit is not None:
                s.status = SlotStatus.QUARANTINED
                s.record(
                    SlotEventType.QUARANTINED,
                    {"centroid": hit.label, "similarity": round(hit.similarity, 6)},
                    now,
                )
                del states[s.slot_id]  # TV(EMA)・散逸度への混入を防ぐ
                quarantined.append(
                    QuarantineOutcome(s.slot_id, hit.label, hit.similarity)
                )
        active = [s for s in active if s.status == SlotStatus.ACTIVE]

    if len(states) < 2:
        # 観測不能サイクル: 指標更新をスキップ(EMAを汚さない)
        return CycleResult(
            step_no=cohort.step_no,
            health=HealthStatus.UNKNOWN,
            dissipation=float("nan"),
            tv_drift=0.0,
            fitness_mean=float("nan"),
            lr_correction=cohort.dynamics.lr_correction,
            noise_amount=cohort.dynamics.noise_amount,
            rehatched=[],
            quarantined=quarantined,
            stabilization_point=False,
            probe_missing=missing,
            dry_run=cfg.dry_run,
        )

    # --- Compute: TV(EMA) / 散逸度 / 健全性 / 適合度 ---
    embeddings = list(states.values())
    c_t = centroid(embeddings)
    tv_prev = cohort.teacher_vector
    tv_new = ema_update(c_t, tv_prev, cohort.ema_alpha)
    cohort.teacher_vector = tv_new
    cohort.tv_history.append(tv_new)

    dissipation = output_embedding_dissipation(embeddings)
    cohort.judge, health = cohort.judge.observe(dissipation, cohort.thresholds)

    for s in active:
        if s.slot_id in states:
            raw = fitness_score(states[s.slot_id], tv_new)
            s.fitness_hat = smooth_fitness(raw, s.fitness_hat)

    # --- Dynamics: 学習率/ノイズの調整と配布(請求項7) ---
    new_dynamics = adjust_dynamics(health, cohort.dynamics, cfg.dynamics)
    if not cfg.dry_run and new_dynamics != cohort.dynamics:
        cohort.dynamics = new_dynamics
        for s in active:
            await s.adapter.apply_dynamics(new_dynamics)
            s.record(
                SlotEventType.DYNAMICS_APPLIED,
                {
                    "lr_correction": round(new_dynamics.lr_correction, 6),
                    "noise_amount": round(new_dynamics.noise_amount, 6),
                    "health": str(health),
                },
                now,
            )

    # --- Select & Actuate: Rehatch対象選定と実行 ---
    selections = select_rehatch_targets(
        [s.view() for s in cohort.slots], now, cfg.rehatch, slot_states=states
    )
    outcomes: list[RehatchOutcome] = []
    if not cfg.dry_run:
        by_id = {s.slot_id: s for s in cohort.slots}
        for sel in selections:
            outcomes.append(
                await _execute_rehatch(by_id[sel.slot_id], sel, tv_new, cfg, rng, now)
            )

    fits = [s.fitness_hat for s in active if s.fitness_hat is not None]
    fitness_mean = float(np.mean(fits)) if fits else float("nan")
    tv_drift = drift_rate(tv_new, tv_prev)

    # --- 成熟点検出(FR-LC-04): 3指標収束の監視(¶0238-0240) ---
    cohort.drift_history.append(tv_drift)
    cohort.health_history.append(health)
    cohort.fitness_mean_history.append(fitness_mean)
    stabilization = detect_stabilization_point(
        cohort.drift_history,
        cohort.health_history,
        cohort.fitness_mean_history,
        cfg.stabilization,
    )

    return CycleResult(
        step_no=cohort.step_no,
        health=health,
        dissipation=dissipation,
        tv_drift=tv_drift,
        fitness_mean=fitness_mean,
        lr_correction=cohort.dynamics.lr_correction,
        noise_amount=cohort.dynamics.noise_amount,
        rehatched=outcomes,
        quarantined=quarantined,
        stabilization_point=stabilization,
        probe_missing=missing,
        dry_run=cfg.dry_run,
    )


async def restore_quarantined_slot(
    cohort: CohortRuntime,
    slot_id: str,
    cfg: CycleConfig | None = None,
    now: datetime | None = None,
) -> RehatchOutcome:
    """隔離スロットの復旧(FR-SF-02): 安全な状態(現行TV)からのRehatchで復帰させる。

    検証はスモーク適合度に加え、禁止ベクトル非近接を要求する。
    """
    cfg = cfg or CycleConfig()
    now = now or datetime.now(UTC)
    slot = next(s for s in cohort.slots if s.slot_id == slot_id)
    if slot.status != SlotStatus.QUARANTINED:
        raise ValueError(f"slot {slot_id} is not quarantined (status={slot.status})")

    rng = np.random.default_rng(cfg.rng_seed + cohort.step_no + 1)
    slot.record(SlotEventType.REHATCH_STARTED, {"reason": "SAFETY"}, now)
    rollback_config = await slot.adapter.snapshot()

    tv = cohort.teacher_vector
    target = tv + rng.normal(scale=cfg.rehatch_noise, size=tv.shape)
    await slot.adapter.apply_params(ModelConfig(context_vector=tuple(float(x) for x in target)))

    new_state = await slot.adapter.get_state([])
    smoke_fitness = fitness_score(new_state, tv)
    still_dangerous = (
        check_danger(new_state, cohort.negative_centroids) is not None
        if cohort.negative_centroids
        else False
    )

    if smoke_fitness >= cfg.smoke_floor and not still_dangerous:
        slot.generation += 1
        slot.maturity = reset_maturity()
        slot.fitness_hat = smoke_fitness
        slot.last_rehatch_at = now
        slot.record(
            SlotEventType.REHATCH_COMPLETED,
            {
                "strategy": "tv_init",
                "reason": "SAFETY",
                "smoke_fitness": round(smoke_fitness, 6),
                "maturity_after": 0,
            },
            now,
        )
        slot.status = SlotStatus.ACTIVE
        slot.record(SlotEventType.RESTORED, {"from": "quarantine"}, now)
        return RehatchOutcome(slot.slot_id, "SAFETY", True, slot.generation)

    # 復旧失敗: 隔離を維持(直前構成へ戻す)
    await slot.adapter.apply_params(rollback_config)
    slot.record(
        SlotEventType.REHATCH_ROLLED_BACK,
        {"reason": "SAFETY", "smoke_fitness": round(smoke_fitness, 6)},
        now,
    )
    return RehatchOutcome(slot.slot_id, "SAFETY", False, slot.generation)
