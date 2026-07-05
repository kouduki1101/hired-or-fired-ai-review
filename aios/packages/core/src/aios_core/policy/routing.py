"""タスクルーティング(請求項8 / 明細書 図14-15 / docs/06 §9)。

- 成熟度・適合度の閾値で Veteran / Rookie にクラスタ分類
- 高重要度・高難易度 → Veteran、探索的・低重要度 → Rookie優先(経験付与、¶0190)
- 割当集中(支配的モデル化)の回避
- 決定は候補スナップショットと理由付きで返す(リネージ要件 FR-GV-01)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aios_core.types import (
    Cluster,
    RoutingConfig,
    SlotStatus,
    SlotView,
    TaskDifficulty,
    TaskImportance,
)


@dataclass(frozen=True)
class TaskMeta:
    importance: TaskImportance = TaskImportance.NORMAL
    difficulty: TaskDifficulty = TaskDifficulty.NORMAL
    category: str | None = None


@dataclass(frozen=True)
class CandidateScore:
    slot_id: str
    display_id: str
    cluster: Cluster
    maturity: int
    fitness: float
    score: float


@dataclass(frozen=True)
class RoutingDecision:
    chosen_slot_id: str
    cluster: Cluster
    reason: str
    candidates: list[CandidateScore] = field(default_factory=list)


class NoRoutableSlotError(Exception):
    """稼働中スロットが存在しない。"""


def classify_cluster(slot: SlotView, cfg: RoutingConfig) -> Cluster:
    is_veteran = (
        slot.maturity >= cfg.maturity_threshold
        and (slot.fitness_hat or 0.0) >= cfg.fitness_threshold
    )
    return Cluster.VETERAN if is_veteran else Cluster.ROOKIE


def _score(slot: SlotView, meta: TaskMeta, cfg: RoutingConfig) -> float:
    affinity = slot.category_affinity.get(meta.category, 0.0) if meta.category else 0.0
    return (
        cfg.w_fitness * (slot.fitness_hat or 0.0)
        + cfg.w_affinity * affinity
        - cfg.w_load * slot.load
    )


_DEFAULT_CFG = RoutingConfig()


def route_task(
    meta: TaskMeta,
    slots: list[SlotView],
    cfg: RoutingConfig = _DEFAULT_CFG,
) -> RoutingDecision:
    pool = [s for s in slots if s.status == SlotStatus.ACTIVE]
    if not pool:
        raise NoRoutableSlotError("no ACTIVE slot available")

    clusters = {s.slot_id: classify_cluster(s, cfg) for s in pool}
    veterans = [s for s in pool if clusters[s.slot_id] == Cluster.VETERAN]
    rookies = [s for s in pool if clusters[s.slot_id] == Cluster.ROOKIE]

    demanding = meta.importance == TaskImportance.HIGH or meta.difficulty == TaskDifficulty.HARD
    if demanding:
        cand, reason = (veterans, "high_importance_to_veteran") if veterans else (
            pool,
            "veteran_unavailable_fallback",
        )
    else:
        cand, reason = (rookies, "exploratory_to_rookie") if rookies else (
            pool,
            "rookie_unavailable_fallback",
        )

    # 割当集中の回避(¶0159): シェア超過スロットを候補から降格(全滅なら許容)
    relaxed = [s for s in cand if s.assign_share <= cfg.dominance_share]
    if relaxed:
        cand = relaxed
    else:
        reason += "+dominance_relaxed"

    scored = sorted(
        (
            CandidateScore(
                slot_id=s.slot_id,
                display_id=s.display_id,
                cluster=clusters[s.slot_id],
                maturity=s.maturity,
                fitness=s.fitness_hat or 0.0,
                score=_score(s, meta, cfg),
            )
            for s in cand
        ),
        key=lambda c: c.score,
        reverse=True,
    )
    chosen = scored[0]
    return RoutingDecision(
        chosen_slot_id=chosen.slot_id,
        cluster=chosen.cluster,
        reason=reason,
        candidates=scored,
    )
