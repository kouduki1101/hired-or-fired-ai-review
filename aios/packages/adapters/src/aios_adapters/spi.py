"""Model Adapter SPI(docs/03 §4.3 / FR-AD-01)。

「内部パラメータ」は広義に扱う(明細書 ¶0057):
ニューラルネットの結合重みに限らず、システムプロンプト・制御用コンテキストベクトル・
ハイパーパラメータ・知識ベースアクセス条件を含む。ModelConfig がその構成スナップショット。

制御プレーンはこのSPI越しにのみエージェント実体(データプレーン)へ作用する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

import numpy as np
from aios_core.types import DynamicsSignal
from numpy.typing import NDArray

Vector = NDArray[np.float64]


class RehatchStrategy(StrEnum):
    """docs/06 §7 の4戦略。"""

    TV_INIT = "tv_init"  # 手法A: コンテキスト注入
    ADAPTER_REGEN = "adapter_regen"  # 手法B: ハイパーネットワークでアダプタ層再生成
    DISTILLATION = "distillation"  # 手法C: 知識蒸留
    PROMPT_RECOMPOSE = "prompt_recompose"  # LLMエージェント向け(¶0057)


@dataclass(frozen=True)
class ModelConfig:
    """広義の内部パラメータ(構成スナップショット)。model_snapshots.config に対応。"""

    system_prompt: str | None = None
    context_vector: tuple[float, ...] | None = None  # 制御用埋め込み(手法A)
    hyperparams: dict[str, Any] = field(default_factory=dict)  # 温度等
    kb_access_policy: dict[str, Any] = field(default_factory=dict)
    params_uri: str | None = None  # 重み実体への参照(自前ホスト系)


@dataclass(frozen=True)
class AdapterCapabilities:
    """Adapterが宣言する対応能力。Rehatch戦略の選択に使う。"""

    adapter_kind: str
    rehatch_strategies: frozenset[RehatchStrategy]
    state_kind: str  # 'output_embedding' | 'parameters'


@dataclass(frozen=True)
class TaskInput:
    task_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class TaskOutput:
    task_id: str
    payload: dict[str, Any]
    embedding: Vector | None = None  # 安全監視・散逸度④の入力


class Probe(Protocol):
    """定点プローブ(FR-MT-06)。"""

    probe_id: str
    input: dict[str, Any]
    weight: float


@runtime_checkable
class ModelAdapter(Protocol):
    """統一インタフェース(FR-AD-01)。実装は冪等な apply_params を保証すること。"""

    def capabilities(self) -> AdapterCapabilities: ...

    async def invoke(self, task: TaskInput, dynamics: DynamicsSignal) -> TaskOutput: ...

    async def get_state(self, probes: list[Any]) -> Vector:
        """出力埋め込みの重心またはパラメータベクトル(capabilities.state_kind)。"""
        ...

    async def apply_params(self, config: ModelConfig) -> None:
        """Rehatch適用。同一configの再適用は同一状態になること(冪等)。"""
        ...

    async def apply_dynamics(self, signal: DynamicsSignal) -> None:
        """学習率補正・ノイズ量のモデル種別に応じた解釈(請求項7)。"""
        ...

    async def snapshot(self) -> ModelConfig:
        """現在の構成スナップショット(ロールバック・世代保存用)。"""
        ...
