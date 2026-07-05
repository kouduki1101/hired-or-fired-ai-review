"""成熟点(Stabilization Point)検出(明細書 ¶0238-0240 / docs/06 §12)。

3条件の収束:
  1. 教師ベクトル変化率(ドリフト)の定常化
  2. 散逸度が STABLE をwサイクル継続
  3. 平均適合度が十分な水準で横ばい
"""

from __future__ import annotations

import numpy as np

from aios_core.types import HealthStatus, StabilizationConfig

_DEFAULT_CFG = StabilizationConfig()


def detect_stabilization_point(
    tv_drifts: list[float],
    health_history: list[HealthStatus],
    fitness_means: list[float],
    cfg: StabilizationConfig = _DEFAULT_CFG,
) -> bool:
    """直近wサイクル分の系列を受け取り、成熟点なら True。

    系列は古い→新しい順。w未満のデータでは常に False(判定保留)。
    """
    w = cfg.window
    if min(len(tv_drifts), len(health_history), len(fitness_means)) < w:
        return False

    drifts = np.asarray(tv_drifts[-w:], dtype=np.float64)
    fits = np.asarray(fitness_means[-w:], dtype=np.float64)

    tv_settled = bool(drifts.mean() < cfg.tv_drift_eps)
    health_stable = all(h == HealthStatus.STABLE for h in health_history[-w:])
    slope = float(np.polyfit(np.arange(w), fits, 1)[0])
    fitness_flat = (
        abs(slope) < cfg.fitness_slope_eps and float(fits.mean()) >= cfg.fitness_mature_level
    )

    return tv_settled and health_stable and fitness_flat
