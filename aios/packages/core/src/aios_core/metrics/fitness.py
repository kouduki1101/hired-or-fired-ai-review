"""適合度スコア(請求項5)。

明細書 ¶0156: 出力ベクトルと第1の指標(教師ベクトル)とのコサイン類似度を
正規化して適合度スコアとする。
    F_i = ( cos(E_i, TV_t) + 1 ) / 2  ∈ [0, 1]
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float64]

_EPS = 1e-12


def fitness_score(slot_state: Vector, teacher_vector: Vector) -> float:
    """正規化コサイン適合度 ∈ [0, 1]。1=教師ベクトルと完全一致方向。"""
    a = np.asarray(slot_state, dtype=np.float64)
    b = np.asarray(teacher_vector, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"dimension mismatch: state={a.shape}, tv={b.shape}")
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < _EPS or nb < _EPS:
        raise ValueError("zero vector")
    cos = float(a @ b / (na * nb))
    return float(np.clip((cos + 1.0) / 2.0, 0.0, 1.0))


def smooth_fitness(new_score: float, previous_smoothed: float | None, beta: float = 0.5) -> float:
    """F̂_i = β・F_i + (1−β)・F̂_i(prev)。単発ノイズによるRehatch誤発動を防ぐ。

    初回(previous_smoothed=None)は生値をそのまま採用する。
    """
    if not (0.0 < beta <= 1.0):
        raise ValueError(f"beta must be in (0, 1], got {beta}")
    if not (0.0 <= new_score <= 1.0):
        raise ValueError(f"score out of range: {new_score}")
    if previous_smoothed is None:
        return new_score
    return beta * new_score + (1.0 - beta) * previous_smoothed
