"""次元拡張スケーリング(請求項9 / 明細書 図5・¶0091-0098 / FR-SC)。

スロット数(K)を維持したまま、教師ベクトルの次元数を N→N+M へ拡張する。
- 拡張次元には価値軸ラベルを必須で付与(¶0098: 新たな「価値軸」の追加)
- 各スロットの制御ベクトルはゼロパディングで整合(既存学習資産の非破壊、¶0097)
- 禁止ベクトルも同時にパディングし、類似度演算の整合を保つ
- 縮小は監査互換性のため不可(coreのexpand_dimensionが拒否)
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from aios_adapters.spi import ModelConfig
from aios_core.lineage.events import SlotEventType
from aios_core.metrics.teacher import expand_dimension

from aios_orchestrator.runtime import CohortRuntime


async def expand_cohort_dimension(
    cohort: CohortRuntime,
    added_dims: int,
    axis_labels: list[str],
    now: datetime | None = None,
) -> int:
    """N→N+M拡張を無停止で適用し、新しい次元数を返す。"""
    if added_dims < 1:
        raise ValueError("added_dims must be >= 1")
    if len(axis_labels) != added_dims:
        raise ValueError(
            f"axis_labels must name every added dimension: "
            f"expected {added_dims}, got {len(axis_labels)}"
        )
    now = now or datetime.now(UTC)
    old_dim = int(cohort.teacher_vector.shape[0])
    new_dim = old_dim + added_dims

    # 教師ベクトル(第1の指標)の拡張。過去履歴はゼロパディングで比較可能なまま
    cohort.teacher_vector = expand_dimension(cohort.teacher_vector, added_dims)

    # 価値軸レジストリ(FR-SC-01: ラベル必須)
    for i, label in enumerate(axis_labels):
        cohort.value_axes[old_dim + i] = label

    # 禁止ベクトル(安全境界)も同一空間へパディング
    cohort.negative_centroids = [
        replace(nc, vector=tuple(list(nc.vector) + [0.0] * added_dims))
        for nc in cohort.negative_centroids
    ]

    # 各スロットの入力次元整合(ゼロパディング。既存パラメータ非破壊)
    for slot in cohort.slots:
        snap = await slot.adapter.snapshot()
        if snap.context_vector is not None:
            padded = tuple(list(snap.context_vector) + [0.0] * added_dims)
            await slot.adapter.apply_params(ModelConfig(context_vector=padded))
        slot.record(
            SlotEventType.CONFIG_CHANGED,
            {
                "change": "dimension_expanded",
                "from_dim": old_dim,
                "to_dim": new_dim,
                "axis_labels": axis_labels,
            },
            now,
        )
    return new_dim
