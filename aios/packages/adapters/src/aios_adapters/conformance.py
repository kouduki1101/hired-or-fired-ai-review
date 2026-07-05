"""Adapter適合テストキット(NFR-MT-04)。

サードパーティAdapterが制御ループに安全に載ることを検証する共通チェック。
各AdapterのテストはこのキットをNew済みインスタンスに対して呼ぶだけでよい。
"""

from __future__ import annotations

import numpy as np
from aios_core.types import DynamicsSignal

from aios_adapters.spi import ModelAdapter, ModelConfig, TaskInput


async def assert_adapter_conformance(adapter: ModelAdapter) -> None:
    caps = adapter.capabilities()
    assert caps.adapter_kind, "adapter_kind must be non-empty"
    assert caps.rehatch_strategies, "at least one rehatch strategy must be declared"
    assert caps.state_kind in ("output_embedding", "parameters")

    # 状態取得: 有限値のベクトルを返す
    state = await adapter.get_state([])
    assert state.ndim == 1 and state.size > 0
    assert bool(np.isfinite(state).all()), "state vector must be finite"

    # スナップショット→再適用の冪等性(ロールバックの前提)
    snap = await adapter.snapshot()
    assert isinstance(snap, ModelConfig)
    await adapter.apply_params(snap)
    await adapter.apply_params(snap)  # 二重適用しても壊れない
    restored = await adapter.snapshot()
    assert restored == snap, "apply_params(snapshot()) must be idempotent"

    # ダイナミクス受理(解釈は自由だが受理は必須)
    await adapter.apply_dynamics(DynamicsSignal(lr_correction=0.5, noise_amount=0.1))
    await adapter.apply_dynamics(DynamicsSignal())  # 基準値へ戻す

    # 推論: task_idを保存して返す
    task = TaskInput(task_id="conf-1", payload={"ping": True})
    out = await adapter.invoke(task, DynamicsSignal())
    assert out.task_id == "conf-1"
