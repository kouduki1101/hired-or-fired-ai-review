"""知識アーカイブとマッチング(docs/06 §7 / 明細書のアーカイブ継承)。

Rehatch で置き換えられる世代の構成は破棄せずアーカイブし、以後の Rehatch では

    archive* = argmax_{a ∈ archives, a.distill_allowed} [ fitness(a.tv, TV_t) · w(a.best_score) ]

で最も現在の教師ベクトルに近い高成績アーカイブを継承元として選ぶ。
類似度は適合度と同じ正規化 (cos+1)/2(請求項5)、スコア重み w は [0,1] クリップ。
純関数・NumPy のみ(ADR-002)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float64]


@dataclass(frozen=True)
class ArchiveEntry:
    """アーカイブ1件。config は広義の内部パラメータのスナップショット(dict表現)。"""

    archive_id: str
    tv: Vector  # この構成が適合していた当時の教師ベクトル
    config: dict  # ModelConfig 相当(system_prompt / context_vector / ...)
    best_score: float  # 当時の到達適合度(0..1)
    source_slot_id: str
    source_generation: int
    archived_at: datetime
    distill_allowed: bool = True


def _cos(a: Vector, b: Vector) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def archive_match_score(entry: ArchiveEntry, tv: Vector) -> float:
    """(cos+1)/2 × clip(best_score, 0, 1)。次元不一致は共通次元で比較する。"""
    dim = min(entry.tv.shape[0], tv.shape[0])
    similarity = (_cos(entry.tv[:dim], tv[:dim]) + 1.0) / 2.0
    weight = float(np.clip(entry.best_score, 0.0, 1.0))
    return similarity * weight


def select_archive(
    archives: list[ArchiveEntry], tv: Vector, *, min_score: float = 0.0
) -> ArchiveEntry | None:
    """継承元アーカイブを選ぶ。distill_allowed のみ対象、閾値未満なら None。"""
    best: ArchiveEntry | None = None
    best_value = min_score
    for entry in archives:
        if not entry.distill_allowed:
            continue
        value = archive_match_score(entry, tv)
        if value > best_value:
            best, best_value = entry, value
    return best
