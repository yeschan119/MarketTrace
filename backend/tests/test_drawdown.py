"""Tests for the trailing-window drawdown core (drop screener, Feature 1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from markettrace.impact.drawdown import (
    MIN_POINTS,
    DrawdownResult,
    PricePoint,
    classify_drop,
    compute_drawdown,
)


def _series(closes: list[float], *, start: date = date(2026, 1, 1)) -> list[PricePoint]:
    """Build daily PricePoints from a list of adj_closes on consecutive days."""
    return [PricePoint(date=start + timedelta(days=i), adj_close=c) for i, c in enumerate(closes)]


def test_drawdown_from_trailing_high() -> None:
    # High 120 mid-window, ends at 90 -> -25%.
    result = compute_drawdown(_series([100, 110, 120, 105, 90]), min_points=3)
    assert result is not None
    assert result.high_price == 120
    assert result.current_price == 90
    assert result.drawdown == pytest.approx(90 / 120 - 1)


def test_current_is_the_high_gives_zero() -> None:
    result = compute_drawdown(_series([80, 90, 100]), min_points=3)
    assert result is not None
    assert result.drawdown == pytest.approx(0.0)
    assert result.high_date == result.current_date


def test_unsorted_input_is_ordered_by_date() -> None:
    pts = _series([100, 120, 90])
    shuffled = [pts[2], pts[0], pts[1]]
    result = compute_drawdown(shuffled, min_points=3)
    assert result is not None
    # Current = latest date (the 90 bar), high = 120.
    assert result.current_price == 90
    assert result.high_price == 120


def test_only_last_window_bars_considered() -> None:
    # A 200 spike outside the trailing window must not count as the high.
    closes = [200] + [100, 110, 105, 95]
    result = compute_drawdown(_series(closes), window=4, min_points=3)
    assert result is not None
    assert result.high_price == 110  # 200 excluded
    assert result.window_points == 4


def test_insufficient_points_returns_none() -> None:
    assert compute_drawdown(_series([100, 90]), min_points=3) is None


def test_default_min_points_gate() -> None:
    too_few = _series([100.0] * (MIN_POINTS - 1))
    assert compute_drawdown(too_few) is None
    enough = _series([100.0] * MIN_POINTS)
    assert compute_drawdown(enough) is not None


def test_empty_and_bad_data_return_none() -> None:
    assert compute_drawdown([]) is None
    assert compute_drawdown(_series([0.0, 0.0, 0.0]), min_points=3) is None


def test_latest_date_tracks_current_for_staleness() -> None:
    result = compute_drawdown(_series([100, 95, 90]), min_points=3)
    assert isinstance(result, DrawdownResult)
    assert result.latest_date == result.current_date == date(2026, 1, 3)


# ---------------------------------------------------------------------------
# classify_drop
# ---------------------------------------------------------------------------


def test_classify_no_recent_events_is_unexplained() -> None:
    assert classify_drop("bearish", 0) == "unexplained_drop"
    assert classify_drop(None, 0) == "unexplained_drop"


def test_classify_bearish_with_recent_events_is_persistent_risk() -> None:
    assert classify_drop("bearish", 3) == "persistent_risk"


def test_classify_non_bearish_with_recent_events_is_overreaction() -> None:
    assert classify_drop("bullish", 2) == "possible_overreaction"
    assert classify_drop("neutral", 1) == "possible_overreaction"
    assert classify_drop(None, 1) == "possible_overreaction"
