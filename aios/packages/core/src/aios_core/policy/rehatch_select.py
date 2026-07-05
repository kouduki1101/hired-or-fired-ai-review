"""Rehatch対象選定(明細書 図12 S1222 / ¶0157-0160 / docs/06 §6)。

選定基準(組合せ):
  a. 適合度が下限基準未満(請求項5)
  b. 過剰適合・支配的モデル・回答固定化(¶0158-0159)
  c. 役割重複クラスタから最高適合の1体を残し他を対象化(¶0160)
  d. 進化係数の停滞(拡張指標、有効時のみ)

ガード: rehatch_lock / cooldown / 1サイクル上限(K×max_ratio)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from numpy.typing import NDArray

from aios_core.types import RehatchReason, RehatchSelectConfig, SlotStatus, SlotView

Vector = NDArray[np.float64]

# 選定理由の優先度(小さいほど優先)。上限適用時の切り捨て順に使う
_PRIORITY: dict[RehatchReason, int] = {
    RehatchReason.LOW_FITNESS: 0,
    RehatchReason.ROLE_DUP: 1,
    RehatchReason.DOMINANT: 2,
    RehatchReason.OVERFIT: 3,
    RehatchReason.PATTERN_LOCK: 4,
    RehatchReason.STAGNANT: 5,
}


@dataclass(frozen=True)
class RehatchSelection:
    slot_id: str
    reason: RehatchReason


def _eligible(slot: SlotView, now: datetime, cfg: RehatchSelectConfig) -> bool:
    if slot.status != SlotStatus.ACTIVE:
        return False
    if slot.rehatch_lock:  # 削除保護フラグ(明細書 図7)
        return False
    in_cooldown = slot.last_rehatch_at is not None and now - slot.last_rehatch_at < timedelta(
        seconds=cfg.cooldown_seconds
    )
    return not in_cooldown


def _duplicate_groups(
    slots: list[SlotView], states: dict[str, Vector], threshold: float
) -> list[list[SlotView]]:
    """ペア類似度 > threshold の連結成分(Union-Find)。stateがあるスロットのみ対象。"""
    items = [s for s in slots if s.slot_id in states]
    n = len(items)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    normed = []
    for s in items:
        v = np.asarray(states[s.slot_id], dtype=np.float64)
        normed.append(v / np.linalg.norm(v))
    for i in range(n):
        for j in range(i + 1, n):
            if float(normed[i] @ normed[j]) > threshold:
                union(i, j)

    groups: dict[int, list[SlotView]] = {}
    for i, s in enumerate(items):
        groups.setdefault(find(i), []).append(s)
    return [g for g in groups.values() if len(g) > 1]


_DEFAULT_CFG = RehatchSelectConfig()


def select_rehatch_targets(
    slots: list[SlotView],
    now: datetime,
    cfg: RehatchSelectConfig = _DEFAULT_CFG,
    slot_states: dict[str, Vector] | None = None,
) -> list[RehatchSelection]:
    """対象と理由のリストを返す(優先度順、上限適用済み)。

    slot_states: 役割重複判定(¶0160)に使う状態ベクトル。省略時は重複判定をスキップ。
    """
    eligible = [s for s in slots if _eligible(s, now, cfg)]
    reasons: dict[str, RehatchReason] = {}

    for s in eligible:
        if s.fitness_hat is None:
            continue  # 未計測スロットは判断材料がないため対象外
        if s.fitness_hat < cfg.f_lower:
            reasons[s.slot_id] = RehatchReason.LOW_FITNESS
        elif s.assign_share > cfg.dominance_share:
            reasons[s.slot_id] = RehatchReason.DOMINANT
        elif s.fitness_hat > cfg.f_upper:
            reasons[s.slot_id] = RehatchReason.OVERFIT
        elif s.output_entropy is not None and s.output_entropy < cfg.entropy_floor:
            reasons[s.slot_id] = RehatchReason.PATTERN_LOCK
        elif (
            cfg.stagnation_floor is not None
            and s.evolution_coeff is not None
            and s.evolution_coeff < cfg.stagnation_floor
        ):
            reasons[s.slot_id] = RehatchReason.STAGNANT

    # 役割重複(¶0160): 最高(fitness, maturity)の1体を残し、他を対象化
    if slot_states:
        for grp in _duplicate_groups(eligible, slot_states, cfg.dup_similarity):
            keep = max(grp, key=lambda s: (s.fitness_hat or 0.0, s.maturity))
            for s in grp:
                if s.slot_id != keep.slot_id and s.slot_id not in reasons:
                    reasons[s.slot_id] = RehatchReason.ROLE_DUP

    # 優先度順に1サイクル上限を適用(群全体の不安定化防止)
    cap = max(1, int(len(slots) * cfg.max_ratio)) if reasons else 0
    ordered = sorted(reasons.items(), key=lambda kv: _PRIORITY[kv[1]])
    return [RehatchSelection(slot_id=sid, reason=r) for sid, r in ordered[:cap]]
