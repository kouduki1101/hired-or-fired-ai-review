"""テナント単位レート制限(API4: リソース消費制限、脅威モデル §5-1)。

プロセス内トークンバケット。認証済みテナントをキーに、毎秒 `rps` トークン補充・
上限 `burst` で消費する。分散構成では前段(Ingress/APIゲートウェイ)または
共有ストア実装に差し替える前提の第一防御線。

有効化: AIOS_RATE_LIMIT_RPS を設定(未設定なら無効=素通し)。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    rps: float
    burst: int

    @classmethod
    def from_env(cls) -> RateLimitConfig | None:
        raw = os.environ.get("AIOS_RATE_LIMIT_RPS")
        if not raw:
            return None
        rps = float(raw)
        burst = int(os.environ.get("AIOS_RATE_LIMIT_BURST", str(max(1, int(rps * 2)))))
        return cls(rps=rps, burst=burst)


class TokenBucketLimiter:
    """テナント -> (トークン残, 最終補充時刻)。単一イベントループ内で使用。"""

    def __init__(self, config: RateLimitConfig) -> None:
        self._cfg = config
        self._state: dict[str, tuple[float, float]] = {}

    def allow(self, tenant: str, now: float | None = None) -> tuple[bool, float]:
        """(許可可否, Retry-After 秒) を返す。許可時の Retry-After は 0。"""
        now = time.monotonic() if now is None else now
        cfg = self._cfg
        tokens, last = self._state.get(tenant, (float(cfg.burst), now))
        tokens = min(cfg.burst, tokens + (now - last) * cfg.rps)
        if tokens >= 1.0:
            self._state[tenant] = (tokens - 1.0, now)
            return True, 0.0
        self._state[tenant] = (tokens, now)
        retry_after = (1.0 - tokens) / cfg.rps if cfg.rps > 0 else 1.0
        return False, retry_after
