"""ダイナミクス調整(請求項7 / 明細書 図13 / docs/06 §8)。

- FIXED(多様性欠如)  → 学習率・ノイズを増加させ探索性を高める(S1323)
- CHAOTIC(過分散)    → 学習率・ノイズを減少させ教師ベクトル追従へ収束(S1324)
- STABLE             → 基準値へ緩やかに回帰
"""

from __future__ import annotations

from aios_core.types import DynamicsConfig, DynamicsSignal, HealthStatus

_DEFAULT_CFG = DynamicsConfig()


def adjust_dynamics(
    health: HealthStatus,
    current: DynamicsSignal,
    cfg: DynamicsConfig = _DEFAULT_CFG,
) -> DynamicsSignal:
    if health == HealthStatus.FIXED:
        lr = min(current.lr_correction * cfg.lr_up, cfg.lr_max)
        noise = min(current.noise_amount + cfg.noise_up, cfg.noise_max)
    elif health == HealthStatus.CHAOTIC:
        lr = max(current.lr_correction * cfg.lr_down, cfg.lr_min)
        noise = max(current.noise_amount - cfg.noise_down, 0.0)
    elif health == HealthStatus.STABLE:
        lr = current.lr_correction + (1.0 - current.lr_correction) * cfg.relax
        noise = current.noise_amount + (cfg.noise_base - current.noise_amount) * cfg.relax
    else:  # UNKNOWN: 判定不能時は現状維持(作用しない)
        return current
    return DynamicsSignal(lr_correction=lr, noise_amount=noise)
