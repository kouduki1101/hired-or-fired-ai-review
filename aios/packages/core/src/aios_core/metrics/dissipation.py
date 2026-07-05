"""散逸度(第2の指標)の演算。

請求項4: 出力の統計的な分散値、モデル間パラメータ距離の平均値、
または群全体の多様性エントロピーのうち少なくともいずれか1つ。

既定は出力埋め込み方式①(明細書 ¶0209: パラメータ比較より計算コストが低い)。
    D_t = 1 − mean_{i<j} cos(E_i, E_j)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float64]

_EPS = 1e-12


def output_embedding_dissipation(embeddings: list[Vector]) -> float:
    """方式①: 平均ペアコサイン類似度の補数。

    正規化行列 X (K×d) について、mean pairwise cos = (‖Σx_i‖² − K) / (K(K−1))
    で O(K·d) で計算する(K² のペア列挙を避ける)。

    返り値は [0, 2]。0=全員同一方向(固着极限)、大きいほど分散。
    """
    k = len(embeddings)
    if k < 2:
        raise ValueError("dissipation requires at least 2 embeddings")
    dims = {e.shape for e in embeddings}
    if len(dims) != 1:
        raise ValueError(f"inconsistent embedding dimensions: {dims}")

    stacked = np.stack([np.asarray(e, dtype=np.float64) for e in embeddings])
    norms = np.linalg.norm(stacked, axis=1, keepdims=True)
    if bool(np.any(norms < _EPS)):
        raise ValueError("zero vector in embeddings")
    x = stacked / norms

    total = x.sum(axis=0)
    sum_sq = float(total @ total)  # ‖Σx_i‖² = K + 2·Σ_{i<j} cos
    mean_pairwise_cos = (sum_sq - k) / (k * (k - 1))
    return float(np.clip(1.0 - mean_pairwise_cos, 0.0, 2.0))


def loss_variance_dissipation(losses: list[float]) -> float:
    """方式③: 共通評価タスクに対する損失値の分散(¶0211)。"""
    if len(losses) < 2:
        raise ValueError("loss variance requires at least 2 values")
    return float(np.var(np.asarray(losses, dtype=np.float64)))


def disagreement_dissipation(choices: list[str]) -> float:
    """方式④: 合意形成の不一致率(¶0210)。 D = 1 − max_c(#c)/K。"""
    if len(choices) < 2:
        raise ValueError("disagreement requires at least 2 choices")
    _, counts = np.unique(np.asarray(choices), return_counts=True)
    return float(1.0 - counts.max() / len(choices))


def entropy_dissipation(choice_probs: list[float]) -> float:
    """方式⑤: 行動選択分布の正規化エントロピー ∈ [0,1]。"""
    p = np.asarray(choice_probs, dtype=np.float64)
    if p.ndim != 1 or p.size < 2:
        raise ValueError("entropy requires a distribution over >= 2 categories")
    if not np.isclose(p.sum(), 1.0, atol=1e-6) or bool(np.any(p < 0)):
        raise ValueError("choice_probs must be a probability distribution")
    nonzero = p[p > _EPS]
    h = float(-(nonzero * np.log(nonzero)).sum())
    return h / float(np.log(p.size))
