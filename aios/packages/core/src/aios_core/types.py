"""値オブジェクトと設定型。

docs/06_algorithm_design.md の記号・既定値に対応する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SlotStatus(StrEnum):
    ACTIVE = "ACTIVE"
    TRAINING = "TRAINING"
    REHATCHING = "REHATCHING"
    QUARANTINED = "QUARANTINED"
    DORMANT = "DORMANT"


class CohortPhase(StrEnum):
    """請求項10: 卵層はINITIALIZINGでのみ動作し、OPERATINGでは非再入。"""

    INITIALIZING = "INITIALIZING"
    CALIBRATING = "CALIBRATING"
    OPERATING = "OPERATING"


class HealthStatus(StrEnum):
    """散逸度(第2の指標)に基づく群健全性判定(明細書 図11 S1126)。"""

    FIXED = "FIXED"  # 固着(多様性欠如)
    STABLE = "STABLE"
    CHAOTIC = "CHAOTIC"  # 過分散
    UNKNOWN = "UNKNOWN"


class RehatchReason(StrEnum):
    """Rehatch対象選定理由(明細書 ¶0157-0160)。"""

    LOW_FITNESS = "LOW_FITNESS"  # 適合度が下限基準未満(請求項5)
    OVERFIT = "OVERFIT"  # 適合度が上限閾値超(過剰適合)
    DOMINANT = "DOMINANT"  # タスク割当集中(既定30%超)
    PATTERN_LOCK = "PATTERN_LOCK"  # 出力エントロピー低下(回答固定化)
    ROLE_DUP = "ROLE_DUP"  # 役割重複(類似度>0.95)
    STAGNANT = "STAGNANT"  # 進化係数停滞
    SAFETY = "SAFETY"  # 安全境界逸脱からの復旧
    MANUAL = "MANUAL"  # 手動指示


class TaskImportance(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TaskDifficulty(StrEnum):
    HARD = "hard"
    NORMAL = "normal"
    EASY = "easy"
    EXPLORATORY = "exploratory"


class Cluster(StrEnum):
    """成熟度×適合度によるクラスタ(明細書 図15)。"""

    VETERAN = "veteran"
    ROOKIE = "rookie"


@dataclass(frozen=True)
class SlotView:
    """ポリシー判断に必要なスロットの読み取りスナップショット(投影)。"""

    slot_id: str
    display_id: str
    status: SlotStatus
    generation: int
    maturity: int
    fitness_hat: float | None  # 平滑化済み適合度 [0,1]。未計測はNone
    rehatch_lock: bool = False
    last_rehatch_at: datetime | None = None
    assign_share: float = 0.0  # 直近窓のタスク割当シェア [0,1]
    output_entropy: float | None = None  # 正規化エントロピー [0,1]
    evolution_coeff: float | None = None  # 進化係数(検証スコア改善率)
    category_affinity: dict[str, float] = field(default_factory=dict)  # 興味関数
    load: float = 0.0  # 現在負荷 [0,1]


@dataclass(frozen=True)
class DynamicsSignal:
    """群全体へ配布される制御信号(請求項7)。"""

    lr_correction: float = 1.0
    noise_amount: float = 0.0


@dataclass(frozen=True)
class HealthThresholds:
    """散逸度の健全性閾値。lower < upper。"""

    lower: float
    upper: float
    hysteresis_cycles: int = 2  # h: 同判定の連続回数で遷移確定

    def __post_init__(self) -> None:
        if not (0.0 <= self.lower < self.upper):
            raise ValueError(f"invalid thresholds: lower={self.lower}, upper={self.upper}")
        if self.hysteresis_cycles < 1:
            raise ValueError("hysteresis_cycles must be >= 1")


@dataclass(frozen=True)
class DynamicsConfig:
    """docs/06 §8 の既定値。"""

    lr_up: float = 1.5
    lr_down: float = 0.6
    lr_max: float = 4.0
    lr_min: float = 0.1
    noise_up: float = 0.05
    noise_down: float = 0.05
    noise_max: float = 0.5
    noise_base: float = 0.05
    relax: float = 0.2  # STABLE時の基準回帰率


@dataclass(frozen=True)
class RehatchSelectConfig:
    """docs/06 §6/§13 の既定値。"""

    f_lower: float = 0.4
    f_upper: float = 0.97
    dominance_share: float = 0.30
    entropy_floor: float = 0.10
    stagnation_floor: float | None = None  # Noneなら進化係数判定を無効(拡張指標)
    dup_similarity: float = 0.95
    max_ratio: float = 0.10  # 1サイクルの同時Rehatch上限(K比)
    cooldown_seconds: int = 24 * 3600


@dataclass(frozen=True)
class RoutingConfig:
    """docs/06 §9。"""

    maturity_threshold: int = 1000  # θ_m
    fitness_threshold: float = 0.7  # θ_f
    dominance_share: float = 0.30
    w_fitness: float = 1.0
    w_affinity: float = 0.5
    w_load: float = 0.5


@dataclass(frozen=True)
class StabilizationConfig:
    """成熟点検出(docs/06 §12)。"""

    window: int = 12  # w
    tv_drift_eps: float = 0.005
    fitness_slope_eps: float = 0.002
    fitness_mature_level: float = 0.7
