"""群健全性判定(明細書 図11 S1126 / docs/06 §3.1)。

生値判定:
    D_t < L        → FIXED(固着)
    L ≤ D_t ≤ U    → STABLE
    D_t > U        → CHAOTIC(発散)

ヒステリシス: 同一の生値判定が h 回連続したときのみ確定状態を遷移させ、
閾値近傍での発振(制御信号のバタつき)を防ぐ。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from aios_core.types import HealthStatus, HealthThresholds


def classify_raw(dissipation: float, thresholds: HealthThresholds) -> HealthStatus:
    """ヒステリシスを適用しない瞬時判定。"""
    if dissipation < 0.0:
        raise ValueError(f"dissipation must be non-negative, got {dissipation}")
    if dissipation < thresholds.lower:
        return HealthStatus.FIXED
    if dissipation > thresholds.upper:
        return HealthStatus.CHAOTIC
    return HealthStatus.STABLE


@dataclass(frozen=True)
class HealthJudge:
    """確定状態と連続カウントを保持する不変の判定器。

    使い方: judge, confirmed = judge.observe(d, thresholds)
    (純関数スタイル: observeは新しいHealthJudgeを返す)
    """

    confirmed: HealthStatus = HealthStatus.UNKNOWN
    candidate: HealthStatus = HealthStatus.UNKNOWN
    streak: int = 0

    def observe(
        self, dissipation: float, thresholds: HealthThresholds
    ) -> tuple[HealthJudge, HealthStatus]:
        raw = classify_raw(dissipation, thresholds)

        if raw == self.confirmed:
            # 現状維持。候補はリセット
            return replace(self, candidate=raw, streak=0), self.confirmed

        streak = self.streak + 1 if raw == self.candidate else 1
        if streak >= thresholds.hysteresis_cycles or self.confirmed == HealthStatus.UNKNOWN:
            # h回連続(または初回観測)で遷移確定
            new = HealthJudge(confirmed=raw, candidate=raw, streak=0)
            return new, raw
        return replace(self, candidate=raw, streak=streak), self.confirmed
