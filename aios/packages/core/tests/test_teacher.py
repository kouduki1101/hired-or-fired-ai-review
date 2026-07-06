import numpy as np
import pytest
from aios_core.metrics.teacher import (
    centroid,
    drift_rate,
    ema_update,
    expand_dimension,
    pad_to_dimension,
)


def unit(*xs: float) -> np.ndarray:
    v = np.asarray(xs, dtype=np.float64)
    return v / np.linalg.norm(v)


class TestCentroid:
    def test_mean_of_normalized(self) -> None:
        c = centroid([np.array([2.0, 0.0]), np.array([0.0, 3.0])])
        assert c == pytest.approx([0.5, 0.5])  # 正規化後の平均

    def test_rejects_empty_and_mismatched(self) -> None:
        with pytest.raises(ValueError):
            centroid([])
        with pytest.raises(ValueError):
            centroid([np.zeros(3) + 1, np.zeros(4) + 1])


class TestEmaUpdate:
    def test_formula_matches_spec(self) -> None:
        """明細書式: V_new = α・V_current + (1−α)・V_old(正規化前)。"""
        cur, old, alpha = unit(1, 0), unit(0, 1), 0.1
        tv = ema_update(cur, old, alpha)
        expected = alpha * cur + (1 - alpha) * old
        expected /= np.linalg.norm(expected)
        assert tv == pytest.approx(expected)

    def test_alpha_one_follows_current(self) -> None:
        tv = ema_update(unit(1, 0), unit(0, 1), alpha=1.0)
        assert tv == pytest.approx(unit(1, 0))

    def test_small_alpha_preserves_history(self) -> None:
        """αが小さいほど旧TV(歴史)に近い = 短期変動の抑制(請求項3)。"""
        cur, old = unit(1, 0), unit(0, 1)
        near = ema_update(cur, old, alpha=0.01)
        far = ema_update(cur, old, alpha=0.9)
        assert near @ old > far @ old

    def test_invalid_alpha(self) -> None:
        for bad in (0.0, -0.1, 1.5):
            with pytest.raises(ValueError):
                ema_update(unit(1, 0), unit(0, 1), alpha=bad)


class TestDrift:
    def test_zero_for_same_direction(self) -> None:
        assert drift_rate(unit(1, 1), unit(2, 2)) == pytest.approx(0.0, abs=1e-9)

    def test_positive_for_rotation(self) -> None:
        assert drift_rate(unit(1, 0), unit(0, 1)) == pytest.approx(1.0)


class TestDimensionExpansion:
    def test_expand_appends_zeros(self) -> None:
        """請求項9: 次元拡張。既存成分は非破壊。"""
        tv = unit(1, 2, 3)
        expanded = expand_dimension(tv, 2)
        assert expanded.shape == (5,)
        assert expanded[:3] == pytest.approx(tv)
        assert expanded[3:] == pytest.approx([0.0, 0.0])

    def test_shrink_forbidden(self) -> None:
        with pytest.raises(ValueError):
            expand_dimension(unit(1, 2), 0)

    def test_pad_for_history_compat(self) -> None:
        old = unit(1, 0)
        padded = pad_to_dimension(old, 4)
        assert padded.shape == (4,)
        # 拡張後空間でも旧TVとの比較(ドリフト計算)が成立する
        assert drift_rate(padded, expand_dimension(old, 2)) == pytest.approx(0.0, abs=1e-9)
        with pytest.raises(ValueError):
            pad_to_dimension(unit(1, 2, 3), 2)
