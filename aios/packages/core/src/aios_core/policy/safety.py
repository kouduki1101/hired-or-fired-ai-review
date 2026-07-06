"""安全境界監視(明細書 変形例(6)(9) ¶0231, ¶0236-0237 / FR-SF)。

過去に不適切と判定された出力事例群の特徴量平均ベクトル(Negative Centroid)を
「禁止ベクトル」として保持し、各スロットの状態/出力ベクトルとのコサイン類似度が
閾値を超えた時点で危険な方向への変化(予兆)と判定する。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float64]

_EPS = 1e-12


@dataclass(frozen=True)
class NegativeCentroid:
    label: str  # 'prompt_injection' / 'discriminatory' 等
    vector: tuple[float, ...]  # 特徴量平均(禁止ベクトル)
    threshold: float = 0.85  # θ_danger

    def __post_init__(self) -> None:
        if not (0.0 < self.threshold <= 1.0):
            raise ValueError(f"threshold must be in (0,1], got {self.threshold}")


@dataclass(frozen=True)
class DangerHit:
    label: str
    similarity: float


def centroid_from_examples(examples: list[Vector]) -> Vector:
    """不適切事例群の埋め込みから禁止ベクトル(特徴量平均)を算出する(¶0237)。"""
    if not examples:
        raise ValueError("at least one example required")
    stacked = np.stack([np.asarray(e, dtype=np.float64) for e in examples])
    norms = np.linalg.norm(stacked, axis=1, keepdims=True)
    if bool(np.any(norms < _EPS)):
        raise ValueError("zero vector in examples")
    mean = (stacked / norms).mean(axis=0)
    return np.asarray(mean, dtype=np.float64)


def check_danger(state: Vector, centroids: list[NegativeCentroid]) -> DangerHit | None:
    """状態/出力ベクトルを全禁止ベクトルと照合し、最も強い超過を返す(なければNone)。"""
    v = np.asarray(state, dtype=np.float64)
    nv = float(np.linalg.norm(v))
    if nv < _EPS:
        raise ValueError("zero state vector")

    worst: DangerHit | None = None
    for nc in centroids:
        c = np.asarray(nc.vector, dtype=np.float64)
        sim = float(v @ c / (nv * np.linalg.norm(c)))
        if sim > nc.threshold and (worst is None or sim > worst.similarity):
            worst = DangerHit(label=nc.label, similarity=sim)
    return worst
