"""AnthropicAgentAdapter のスタブ検証(実APIは呼ばない)。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest
from aios_adapters.anthropic_agent import AnthropicAgentAdapter
from aios_adapters.conformance import assert_adapter_conformance
from aios_adapters.spi import ModelConfig, RehatchStrategy, TaskInput
from aios_core.types import DynamicsSignal

DIM = 16


async def stub_embedder(text: str) -> np.ndarray:
    """決定的な模擬埋め込み: テキストのSHA-256から生成。"""
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
    return np.random.default_rng(seed).normal(size=DIM)


@dataclass
class _Block:
    text: str


@dataclass
class _Response:
    content: list[_Block]


@dataclass
class _StubMessages:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        return _Response(content=[_Block(text=f"echo:{kwargs['system'][:20]}")])


@dataclass
class _StubClient:
    messages: _StubMessages = field(default_factory=_StubMessages)


def make() -> tuple[AnthropicAgentAdapter, _StubClient]:
    client = _StubClient()
    adapter = AnthropicAgentAdapter(
        client=client,
        embedder=stub_embedder,
        system_prompt="丁寧で正確なカスタマーサポートを行う。",
    )
    return adapter, client


class TestConformance:
    async def test_conforms_to_spi(self) -> None:
        adapter, _ = make()
        await assert_adapter_conformance(adapter)

    def test_declares_prompt_recompose(self) -> None:
        adapter, _ = make()
        caps = adapter.capabilities()
        assert RehatchStrategy.PROMPT_RECOMPOSE in caps.rehatch_strategies


class TestInvoke:
    async def test_passes_system_prompt_and_returns_embedding(self) -> None:
        adapter, client = make()
        out = await adapter.invoke(
            TaskInput(task_id="t1", payload={"messages": [{"role": "user", "content": "hi"}]}),
            DynamicsSignal(),
        )
        assert client.messages.calls[0]["system"].startswith("丁寧で正確")
        assert out.embedding is not None and out.embedding.shape == (DIM,)

    async def test_noise_maps_to_temperature(self) -> None:
        """請求項7のLLM解釈: ノイズ量→温度(docs/06 §8)。"""
        adapter, client = make()
        await adapter.invoke(TaskInput(task_id="a", payload={"input": "x"}), DynamicsSignal())
        base_temp = client.messages.calls[0]["temperature"]

        await adapter.apply_dynamics(DynamicsSignal(noise_amount=0.3))
        await adapter.invoke(TaskInput(task_id="b", payload={"input": "x"}), DynamicsSignal())
        noisy_temp = client.messages.calls[1]["temperature"]
        assert noisy_temp > base_temp
        assert noisy_temp <= 1.0


class TestRehatch:
    async def test_prompt_recompose_changes_behavior_state(self) -> None:
        """Prompt-Recomposeでシステムプロンプトが差し替わり、状態表現も変わる。"""
        adapter, _ = make()
        before = await adapter.get_state([])

        await adapter.apply_params(
            ModelConfig(
                system_prompt="法務専門の慎重なアシスタントとして振る舞う。",
                hyperparams={"temperature": 0.1},
            )
        )
        after = await adapter.get_state([])
        assert not np.allclose(before, after)  # 挙動の代理表現が変化

        snap = await adapter.snapshot()
        assert snap.system_prompt is not None and snap.system_prompt.startswith("法務専門")
        assert snap.hyperparams["temperature"] == pytest.approx(0.1)
