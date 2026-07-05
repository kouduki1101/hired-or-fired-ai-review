import numpy as np
import pytest
from aios_core.metrics.dissipation import (
    disagreement_dissipation,
    entropy_dissipation,
    loss_variance_dissipation,
    output_embedding_dissipation,
)
from aios_core.metrics.fitness import fitness_score, smooth_fitness
from aios_core.metrics.maturity import add_maturity, decay_maturity, reset_maturity


class TestOutputEmbeddingDissipation:
    def test_identical_outputs_mean_fixation(self) -> None:
        """全スロットが同一出力 → 散逸度0(固着の極限)。"""
        e = np.array([1.0, 2.0, 3.0])
        assert output_embedding_dissipation([e, e * 2, e * 3]) == pytest.approx(0.0, abs=1e-9)

    def test_orthogonal_outputs(self) -> None:
        d = output_embedding_dissipation([np.array([1.0, 0.0]), np.array([0.0, 1.0])])
        assert d == pytest.approx(1.0)

    def test_opposite_outputs_max(self) -> None:
        d = output_embedding_dissipation([np.array([1.0, 0.0]), np.array([-1.0, 0.0])])
        assert d == pytest.approx(2.0)

    def test_closed_form_equals_naive_pairwise(self) -> None:
        """O(K·d)の閉形式が素朴なペア列挙と一致する。"""
        rng = np.random.default_rng(42)
        embs = [rng.normal(size=8) for _ in range(15)]
        normed = [e / np.linalg.norm(e) for e in embs]
        pairs = [
            float(normed[i] @ normed[j])
            for i in range(len(embs))
            for j in range(i + 1, len(embs))
        ]
        naive = 1.0 - float(np.mean(pairs))
        assert output_embedding_dissipation(embs) == pytest.approx(naive)

    def test_requires_two(self) -> None:
        with pytest.raises(ValueError):
            output_embedding_dissipation([np.array([1.0, 0.0])])


class TestOtherDissipationStrategies:
    def test_loss_variance(self) -> None:
        assert loss_variance_dissipation([0.5, 0.5, 0.5]) == pytest.approx(0.0)
        assert loss_variance_dissipation([0.0, 1.0]) == pytest.approx(0.25)

    def test_disagreement(self) -> None:
        assert disagreement_dissipation(["a", "a", "a"]) == pytest.approx(0.0)
        assert disagreement_dissipation(["a", "b", "c", "d"]) == pytest.approx(0.75)

    def test_entropy(self) -> None:
        assert entropy_dissipation([1.0, 0.0]) == pytest.approx(0.0)
        assert entropy_dissipation([0.5, 0.5]) == pytest.approx(1.0)
        with pytest.raises(ValueError):
            entropy_dissipation([0.7, 0.7])


class TestFitness:
    def test_aligned_is_one(self) -> None:
        tv = np.array([1.0, 1.0])
        assert fitness_score(tv * 5, tv) == pytest.approx(1.0)

    def test_opposite_is_zero(self) -> None:
        tv = np.array([1.0, 0.0])
        assert fitness_score(-tv, tv) == pytest.approx(0.0)

    def test_orthogonal_is_half(self) -> None:
        assert fitness_score(np.array([0.0, 1.0]), np.array([1.0, 0.0])) == pytest.approx(0.5)

    def test_smoothing(self) -> None:
        assert smooth_fitness(0.8, None) == pytest.approx(0.8)  # 初回は生値
        assert smooth_fitness(0.8, 0.4) == pytest.approx(0.6)  # 0.5·new + 0.5·prev
        # 単発の低スコアでは下限を割りにくい(誤発動防止)
        assert smooth_fitness(0.1, 0.9) == pytest.approx(0.5)


class TestMaturity:
    def test_lifecycle(self) -> None:
        m = add_maturity(0, 100)
        assert m == 100
        assert reset_maturity() == 0  # 全面再配置
        assert decay_maturity(m, 30) == 70  # 部分更新は減算(¶0169)
        assert decay_maturity(10, 50) == 0  # 下限0
