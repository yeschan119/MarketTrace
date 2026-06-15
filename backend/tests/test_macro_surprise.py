"""Unit tests for the deterministic macro-surprise numeric core."""

from __future__ import annotations

from datetime import UTC, date, datetime
from math import sqrt

import pytest

from markettrace.impact.macro_surprise import (
    baseline_expectation,
    build_macro_observations,
    change_scale,
    compute_surprise,
)
from markettrace.providers.base import MacroPoint


def _point(ref: date, value: float, prev: float | None) -> MacroPoint:
    return MacroPoint(
        series_id="CPIAUCSL",
        reference_date=ref,
        released_value=value,
        released_at=datetime(ref.year, ref.month, ref.day, tzinfo=UTC),
        previous_value=prev,
    )


class TestComputeSurprise:
    def test_standardized_value(self):
        assert compute_surprise(110.0, 100.0, 5.0) == pytest.approx(2.0)

    def test_negative_surprise(self):
        assert compute_surprise(95.0, 100.0, 5.0) == pytest.approx(-1.0)

    @pytest.mark.parametrize(
        "released,expected,scale",
        [(None, 100.0, 5.0), (110.0, None, 5.0), (110.0, 100.0, None), (110.0, 100.0, 0.0)],
    )
    def test_missing_or_zero_yields_none(self, released, expected, scale):
        assert compute_surprise(released, expected, scale) is None


class TestBaselineExpectation:
    def test_empty_history_is_none(self):
        assert baseline_expectation([]) is None

    def test_random_walk_returns_last(self):
        assert baseline_expectation([1.0, 2.0, 3.0]) == 3.0


class TestChangeScale:
    def test_insufficient_history_is_none(self):
        assert change_scale([1.0, 2.0]) is None  # < 3 points

    def test_zero_dispersion_is_none(self):
        assert change_scale([5.0, 5.0, 5.0, 5.0]) is None  # all diffs == 0

    def test_sample_std_of_changes(self):
        # changes of [100,102,101] = [2, -1]; sample std (ddof=1) of [2,-1]
        diffs = [2.0, -1.0]
        mean = sum(diffs) / 2
        expected = sqrt(sum((d - mean) ** 2 for d in diffs) / 1)
        assert change_scale([100.0, 102.0, 101.0]) == pytest.approx(expected)


class TestBuildMacroObservations:
    DATES = [date(2024, m, 1) for m in range(1, 6)]
    VALUES = [100.0, 102.0, 101.0, 104.0, 108.0]

    def _points(self):
        prev = None
        pts = []
        for d, v in zip(self.DATES, self.VALUES, strict=True):
            pts.append(_point(d, v, prev))
            prev = v
        return pts

    def test_one_row_per_point_with_provenance(self):
        now = datetime(2026, 6, 15, tzinfo=UTC)
        rows = build_macro_observations(self._points(), now=now)
        assert len(rows) == 5
        assert all(r.first_seen_at == now and r.source == "fred" for r in rows)
        assert [r.reference_date for r in rows] == self.DATES

    def test_early_points_have_no_surprise_no_lookahead(self):
        rows = build_macro_observations(self._points(), now=datetime(2026, 1, 1, tzinfo=UTC))
        # First point has no history -> no expectation/scale.
        assert rows[0].expected_value is None
        assert rows[0].expected_source is None
        assert rows[0].surprise_score is None
        # Points 1-2 have a baseline expectation but too little history for scale.
        assert rows[1].expected_source == "baseline"
        assert rows[1].surprise_score is None

    def test_baseline_surprise_once_scale_available(self):
        rows = build_macro_observations(self._points(), now=datetime(2026, 1, 1, tzinfo=UTC))
        # Point index 3 (104): history [100,102,101], baseline=101,
        # scale = std([2,-1]) -> surprise = (104-101)/scale.
        scale = change_scale([100.0, 102.0, 101.0])
        assert rows[3].expected_value == pytest.approx(101.0)
        assert rows[3].expected_source == "baseline"
        assert rows[3].surprise_score == pytest.approx(3.0 / scale)

    def test_consensus_override(self):
        lookup = {date(2024, 4, 1): 100.0}
        rows = build_macro_observations(
            self._points(), now=datetime(2026, 1, 1, tzinfo=UTC), expected_lookup=lookup
        )
        scale = change_scale([100.0, 102.0, 101.0])
        assert rows[3].expected_value == pytest.approx(100.0)
        assert rows[3].expected_source == "consensus"
        assert rows[3].surprise_score == pytest.approx(4.0 / scale)
