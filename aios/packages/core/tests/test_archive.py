"""知識アーカイブ・マッチング(docs/06 §7)の純関数テスト。"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from aios_core.lineage.archive import ArchiveEntry, archive_match_score, select_archive

NOW = datetime(2026, 7, 18, tzinfo=UTC)


def _entry(tv, score, *, allowed=True, aid="a"):
    return ArchiveEntry(
        archive_id=aid,
        tv=np.asarray(tv, dtype=np.float64),
        config={"system_prompt": f"prompt-{aid}"},
        best_score=score,
        source_slot_id="s1",
        source_generation=0,
        archived_at=NOW,
        distill_allowed=allowed,
    )


class TestMatchScore:
    def test_identical_tv_full_score(self) -> None:
        tv = np.array([1.0, 0.0, 0.0])
        assert archive_match_score(_entry(tv, 1.0), tv) == 1.0

    def test_opposite_tv_zero_similarity(self) -> None:
        tv = np.array([1.0, 0.0, 0.0])
        assert archive_match_score(_entry(-tv, 1.0), tv) == 0.0

    def test_score_weight_clipped(self) -> None:
        tv = np.array([1.0, 0.0])
        assert archive_match_score(_entry(tv, 5.0), tv) == 1.0  # clip上限
        assert archive_match_score(_entry(tv, -1.0), tv) == 0.0  # clip下限

    def test_dimension_mismatch_uses_common_dims(self) -> None:
        entry = _entry([1.0, 0.0], 1.0)
        tv = np.array([1.0, 0.0, 0.0, 0.0])  # 次元拡張後
        assert archive_match_score(entry, tv) == 1.0


class TestSelectArchive:
    def test_argmax_of_similarity_times_score(self) -> None:
        tv = np.array([1.0, 0.0])
        near_low = _entry([1.0, 0.0], 0.4, aid="near-low")
        far_high = _entry([0.0, 1.0], 0.9, aid="far-high")  # cos=0 → (0+1)/2=0.5
        # near-low: 1.0*0.4=0.4 / far-high: 0.5*0.9=0.45 → far-high
        assert select_archive([near_low, far_high], tv).archive_id == "far-high"

    def test_distill_not_allowed_is_skipped(self) -> None:
        tv = np.array([1.0, 0.0])
        blocked = _entry(tv, 1.0, allowed=False, aid="blocked")
        weaker = _entry(tv, 0.5, aid="weaker")
        assert select_archive([blocked, weaker], tv).archive_id == "weaker"

    def test_empty_or_below_floor_returns_none(self) -> None:
        tv = np.array([1.0, 0.0])
        assert select_archive([], tv) is None
        low = _entry(tv, 0.1, aid="low")
        assert select_archive([low], tv, min_score=0.5) is None
