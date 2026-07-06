"""教師ベクトル(第1の指標)の演算。

明細書 図11 S1122-S1123 / 請求項3:
    V_new = α・V_current + (1−α)・V_old
過去の文脈(歴史)を維持しつつ新しい傾向を一部取り込む指数移動平均。

次元拡張(請求項9): スロット数を維持したまま次元数を N→N+M へ拡張する。
旧履歴との比較はゼロパディングで整合させる(docs/06 §10)。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float64]

_EPS = 1e-12


def _l2_normalize(v: Vector) -> Vector:
    norm = float(np.linalg.norm(v))
    if norm < _EPS:
        raise ValueError("cannot normalize zero vector")
    return v / norm


def centroid(embeddings: list[Vector]) -> Vector:
    """群の重心 C_t。入力は各スロットの状態ベクトル(欠測は呼び出し側で除外済み)。

    各ベクトルをL2正規化した上で算術平均を取る(明細書 図11 S1122)。
    """
    if not embeddings:
        raise ValueError("centroid requires at least one embedding")
    dims = {e.shape for e in embeddings}
    if len(dims) != 1:
        raise ValueError(f"inconsistent embedding dimensions: {dims}")
    stacked = np.stack([_l2_normalize(np.asarray(e, dtype=np.float64)) for e in embeddings])
    return np.asarray(stacked.mean(axis=0), dtype=np.float64)


def ema_update(current_centroid: Vector, previous_tv: Vector, alpha: float) -> Vector:
    """TV_t = normalize( α・C_t + (1−α)・TV_{t−1} )。

    α∈(0,1]。小さいほど「歴史」を重視する(既定0.1)。
    """
    if not (0.0 < alpha <= 1.0):
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")
    if current_centroid.shape != previous_tv.shape:
        raise ValueError(
            f"dimension mismatch: centroid={current_centroid.shape}, tv={previous_tv.shape}"
        )
    mixed = alpha * np.asarray(current_centroid, dtype=np.float64) + (1.0 - alpha) * np.asarray(
        previous_tv, dtype=np.float64
    )
    return _l2_normalize(mixed)


def drift_rate(tv_new: Vector, tv_old: Vector) -> float:
    """δ_t = 1 − cos(TV_t, TV_{t−1})。成熟点検出・ダッシュボード用。"""
    a = _l2_normalize(np.asarray(tv_new, dtype=np.float64))
    b = _l2_normalize(np.asarray(tv_old, dtype=np.float64))
    return float(np.clip(1.0 - a @ b, 0.0, 2.0))


def expand_dimension(tv: Vector, added_dims: int) -> Vector:
    """次元拡張: N → N+M。新次元はゼロで初期化(既存学習資産の非破壊、¶0097)。

    縮小は監査互換性のため禁止(added_dims >= 1)。
    """
    if added_dims < 1:
        raise ValueError("added_dims must be >= 1 (dimension reduction is forbidden)")
    return np.concatenate([np.asarray(tv, dtype=np.float64), np.zeros(added_dims)])


def pad_to_dimension(tv: Vector, dimension: int) -> Vector:
    """旧世代TVを現行次元へゼロパディングして比較可能にする(履歴整合)。"""
    current = tv.shape[0]
    if current > dimension:
        raise ValueError(f"cannot shrink vector from {current} to {dimension}")
    if current == dimension:
        return np.asarray(tv, dtype=np.float64)
    return np.concatenate([np.asarray(tv, dtype=np.float64), np.zeros(dimension - current)])
