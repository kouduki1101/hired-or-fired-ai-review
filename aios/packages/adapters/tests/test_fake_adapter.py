import numpy as np
import pytest
from aios_adapters.conformance import assert_adapter_conformance
from aios_adapters.fake import FakeAgentAdapter
from aios_adapters.spi import ModelConfig
from aios_core.types import DynamicsSignal


def make(seed: int = 1) -> FakeAgentAdapter:
    return FakeAgentAdapter(behavior=np.array([1.0, 0.0, 0.0, 0.0]), seed=seed)


class TestConformance:
    async def test_fake_adapter_conforms(self) -> None:
        await assert_adapter_conformance(make())


class TestBehavior:
    async def test_no_noise_is_stationary(self) -> None:
        a = make()
        s1 = await a.get_state([])
        s2 = await a.get_state([])
        assert s1 == pytest.approx(s2)

    async def test_noise_causes_exploration(self) -> None:
        """ノイズ注入(FIXED時の制御)で挙動が拡散する。"""
        a = make()
        await a.apply_dynamics(DynamicsSignal(noise_amount=0.3))
        s1 = await a.get_state([])
        s2 = await a.get_state([])
        assert float(np.linalg.norm(s1 - s2)) > 0.0

    async def test_deterministic_with_same_seed(self) -> None:
        """監査リプレイ要件: 同一シード→同一軌跡。"""
        a, b = make(seed=7), make(seed=7)
        await a.apply_dynamics(DynamicsSignal(noise_amount=0.2))
        await b.apply_dynamics(DynamicsSignal(noise_amount=0.2))
        for _ in range(5):
            sa, sb = await a.get_state([]), await b.get_state([])
            assert sa == pytest.approx(sb)

    async def test_rehatch_via_context_vector(self) -> None:
        """手法A(TV-Init): context_vector適用で挙動が再設定される。"""
        a = make()
        target = np.array([0.0, 1.0, 0.0, 0.0])
        await a.apply_params(ModelConfig(context_vector=tuple(target)))
        assert (await a.get_state([])) == pytest.approx(target)
