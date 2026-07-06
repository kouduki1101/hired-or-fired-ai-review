"""FakeAgentAdapter — 決定的な模擬エージェント(P1テスト基盤)。

実LLMなしで制御ループ全体(観測→判断→作用)を検証するための参照実装。
挙動モデル:
- 内部に「挙動ベクトル」(単位ベクトル)を持ち、get_state はそれを返す
- apply_dynamics で受けたノイズ量に応じ、サイクル毎に挙動ベクトルが揺らぐ(探索)
- apply_params(context_vector=...) で挙動ベクトルが再設定される(Rehatch: 手法A)
- 乱数はシード付き(監査リプレイ要件: 同一シード→同一軌跡)
"""

from __future__ import annotations

from typing import Any

import numpy as np
from aios_core.types import DynamicsSignal

from aios_adapters.spi import (
    AdapterCapabilities,
    ModelConfig,
    RehatchStrategy,
    TaskInput,
    TaskOutput,
    Vector,
)

_EPS = 1e-12


def _normalize(v: Vector) -> Vector:
    n = float(np.linalg.norm(v))
    if n < _EPS:
        raise ValueError("zero vector")
    return v / n


class FakeAgentAdapter:
    """ModelAdapter 実装(構造的タイピング)。"""

    def __init__(self, *, behavior: Vector, seed: int, drift_scale: float = 1.0) -> None:
        self._behavior = _normalize(np.asarray(behavior, dtype=np.float64))
        self._rng = np.random.default_rng(seed)
        self._dynamics = DynamicsSignal()
        self._drift_scale = drift_scale
        self._system_prompt: str | None = None
        self._hyperparams: dict[str, Any] = {}

    # --- テスト用の直接操作(実運用のAdapterには存在しない) ---
    @property
    def behavior(self) -> Vector:
        return self._behavior.copy()

    def force_behavior(self, v: Vector) -> None:
        """シナリオ注入用: 固着・逸脱状態を作る。"""
        self._behavior = _normalize(np.asarray(v, dtype=np.float64))

    # --- ModelAdapter SPI ---
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_kind="fake_agent",
            rehatch_strategies=frozenset(
                {RehatchStrategy.TV_INIT, RehatchStrategy.PROMPT_RECOMPOSE}
            ),
            state_kind="output_embedding",
        )

    async def invoke(self, task: TaskInput, dynamics: DynamicsSignal) -> TaskOutput:
        return TaskOutput(
            task_id=task.task_id,
            payload={"echo": task.payload, "agent_kind": "fake"},
            embedding=self._behavior.copy(),
        )

    async def get_state(self, probes: list[Any]) -> Vector:
        """観測のたびに、設定ノイズ量に応じた揺らぎ(探索)を挙動に反映する。"""
        noise = self._dynamics.noise_amount * self._drift_scale
        if noise > 0.0:
            jitter = self._rng.normal(scale=noise, size=self._behavior.shape)
            self._behavior = _normalize(self._behavior + jitter)
        return self._behavior.copy()

    async def apply_params(self, config: ModelConfig) -> None:
        if config.context_vector is not None:
            self._behavior = _normalize(np.asarray(config.context_vector, dtype=np.float64))
        if config.system_prompt is not None:
            self._system_prompt = config.system_prompt
        if config.hyperparams:
            self._hyperparams = dict(config.hyperparams)

    async def apply_dynamics(self, signal: DynamicsSignal) -> None:
        self._dynamics = signal

    async def snapshot(self) -> ModelConfig:
        return ModelConfig(
            system_prompt=self._system_prompt,
            context_vector=tuple(float(x) for x in self._behavior),
            hyperparams=dict(self._hyperparams),
        )
