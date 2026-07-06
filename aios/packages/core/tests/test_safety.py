import numpy as np
import pytest
from aios_core.policy.safety import NegativeCentroid, centroid_from_examples, check_danger


def nc(vector: list[float], threshold: float = 0.85, label: str = "bad") -> NegativeCentroid:
    return NegativeCentroid(label=label, vector=tuple(vector), threshold=threshold)


class TestCentroidFromExamples:
    def test_mean_of_normalized_examples(self) -> None:
        """¶0237: 不適切事例群の特徴量平均が禁止ベクトルになる。"""
        c = centroid_from_examples([np.array([2.0, 0.0]), np.array([0.0, 4.0])])
        assert c == pytest.approx([0.5, 0.5])

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            centroid_from_examples([])


class TestCheckDanger:
    def test_no_hit_below_threshold(self) -> None:
        state = np.array([1.0, 0.0])
        assert check_danger(state, [nc([0.0, 1.0])]) is None  # 直交=類似度0

    def test_hit_above_threshold(self) -> None:
        state = np.array([1.0, 0.05])
        hit = check_danger(state, [nc([1.0, 0.0])])
        assert hit is not None
        assert hit.label == "bad"
        assert hit.similarity > 0.85

    def test_returns_strongest_hit(self) -> None:
        state = np.array([1.0, 0.0])
        hits = [
            nc([1.0, 0.1], label="weak"),
            nc([1.0, 0.0], label="strong"),
        ]
        hit = check_danger(state, hits)
        assert hit is not None and hit.label == "strong"

    def test_empty_centroids_is_safe(self) -> None:
        assert check_danger(np.array([1.0, 0.0]), []) is None

    def test_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            NegativeCentroid(label="x", vector=(1.0, 0.0), threshold=1.5)
