"""成熟度の更新規則(請求項8 / 明細書 ¶0169)。

- タスク処理・学習で加算
- Rehatch全面再配置 → 初期値(0)にリセット
- 部分更新(アダプタのみ・soft rehatch) → 所定量を減算
"""

from __future__ import annotations


def add_maturity(current: int, delta: int) -> int:
    if current < 0 or delta < 0:
        raise ValueError("maturity and delta must be non-negative")
    return current + delta


def reset_maturity() -> int:
    """全面再配置時: 成熟度を初期値に設定する。"""
    return 0


def decay_maturity(current: int, penalty: int) -> int:
    """部分的な再配置時: 現在の成熟度を所定量だけ減算する(下限0)。"""
    if current < 0 or penalty < 0:
        raise ValueError("maturity and penalty must be non-negative")
    return max(0, current - penalty)
