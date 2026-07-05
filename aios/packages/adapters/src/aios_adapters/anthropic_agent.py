"""AnthropicAgentAdapter — LLM APIエージェント接続(GA既定Adapter、FR-AD-01①)。

制御対象の「内部パラメータ」= システムプロンプト・温度等ハイパーパラメータ・
知識ベースアクセスポリシー(明細書 ¶0057)。Rehatch戦略は Prompt-Recompose。

依存注入設計:
- client: `messages.create(**kwargs)` を持つ任意の非同期クライアント
  (anthropic.AsyncAnthropic 互換。テストではスタブを注入)
- embedder: async (text) -> Vector。出力埋め込みの算出(FR-AD-02)
SDKパッケージへの直接依存を持たないため、adapters は軽量なまま保たれる。
"""

from __future__ import annotations

from typing import Any, Protocol

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

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 1024
BASE_TEMPERATURE = 0.3
# ノイズ量→温度への写像(docs/06 §8: LLMではnoiseを温度・プロンプト摂動幅へ解釈)
NOISE_TO_TEMPERATURE_GAIN = 1.4
MAX_TEMPERATURE = 1.0


class Embedder(Protocol):
    async def __call__(self, text: str) -> Vector: ...


class AnthropicAgentAdapter:
    def __init__(
        self,
        *,
        client: Any,
        embedder: Embedder,
        system_prompt: str,
        model: str = DEFAULT_MODEL,
        hyperparams: dict[str, Any] | None = None,
        kb_access_policy: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._system_prompt = system_prompt
        self._model = model
        self._hyperparams: dict[str, Any] = {"temperature": BASE_TEMPERATURE, **(hyperparams or {})}
        self._kb_access_policy: dict[str, Any] = dict(kb_access_policy or {})
        self._dynamics = DynamicsSignal()

    # --- ModelAdapter SPI ---
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_kind="anthropic_agent",
            rehatch_strategies=frozenset({RehatchStrategy.PROMPT_RECOMPOSE}),
            state_kind="output_embedding",
        )

    def _effective_temperature(self) -> float:
        base = float(self._hyperparams.get("temperature", BASE_TEMPERATURE))
        noisy = base + self._dynamics.noise_amount * NOISE_TO_TEMPERATURE_GAIN
        return min(max(noisy, 0.0), MAX_TEMPERATURE)

    async def invoke(self, task: TaskInput, dynamics: DynamicsSignal) -> TaskOutput:
        messages = task.payload.get("messages") or [
            {"role": "user", "content": str(task.payload.get("input", ""))}
        ]
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=int(self._hyperparams.get("max_tokens", DEFAULT_MAX_TOKENS)),
            temperature=self._effective_temperature(),
            system=self._system_prompt,
            messages=messages,
        )
        text = "".join(
            getattr(block, "text", "") or (block.get("text", "") if isinstance(block, dict) else "")
            for block in response.content
        )
        return TaskOutput(
            task_id=task.task_id,
            payload={"text": text, "model": self._model},
            embedding=await self._embedder(text),
        )

    async def get_state(self, probes: list[Any]) -> Vector:
        """定点プローブへの応答埋め込みの重み付き平均。プローブなしの場合は
        現行システムプロンプトの埋め込みを挙動の代理表現として返す。"""
        if not probes:
            return await self._embedder(self._system_prompt)
        embeddings: list[Vector] = []
        weights: list[float] = []
        for probe in probes:
            out = await self.invoke(
                TaskInput(task_id=f"probe:{probe.probe_id}", payload=probe.input),
                self._dynamics,
            )
            assert out.embedding is not None
            embeddings.append(out.embedding)
            weights.append(float(getattr(probe, "weight", 1.0)))
        w = np.asarray(weights, dtype=np.float64)
        stacked = np.stack(embeddings)
        mean = (stacked * w[:, None]).sum(axis=0) / max(float(w.sum()), _EPS)
        return np.asarray(mean, dtype=np.float64)

    async def apply_params(self, config: ModelConfig) -> None:
        """Prompt-Recompose: システムプロンプト・ハイパラ・KBポリシーの再構成(冪等)。"""
        if config.system_prompt is not None:
            self._system_prompt = config.system_prompt
        if config.hyperparams:
            self._hyperparams = dict(config.hyperparams)
        if config.kb_access_policy:
            self._kb_access_policy = dict(config.kb_access_policy)

    async def apply_dynamics(self, signal: DynamicsSignal) -> None:
        self._dynamics = signal

    async def snapshot(self) -> ModelConfig:
        return ModelConfig(
            system_prompt=self._system_prompt,
            hyperparams=dict(self._hyperparams),
            kb_access_policy=dict(self._kb_access_policy),
        )
