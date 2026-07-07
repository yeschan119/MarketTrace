"""Tests for the mean-reversion rebound backtest (Feature 1, stage 4)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from markettrace.impact.drawdown import PricePoint
from markettrace.impact.rebound_backtest import (
    find_rebound_signals,
    rebound_backtest,
)


def _series(closes: list[float], *, start: date = date(2026, 1, 1)) -> list[PricePoint]:
    return [PricePoint(date=start + timedelta(days=i), adj_close=c) for i, c in enumerate(closes)]


def test_no_signal_when_no_drop() -> None:
    signals, dropped = find_rebound_signals(
        _series([100.0] * 15), threshold=-0.15, window=10, horizon=3, min_points=5
    )
    assert signals == []
    assert dropped == 0


def test_detects_drop_and_scores_forward_return() -> None:
    # Flat at 100, a single-bar cliff to 80 (-20%), then recovery — an unambiguous
    # entry bar (the cliff), so the test does not depend on where a ramp crosses.
    closes = [100.0] * 12 + [80, 84, 88]
    signals, dropped = find_rebound_signals(
        _series(closes), threshold=-0.15, window=12, horizon=2, min_points=5
    )
    assert dropped == 0
    assert len(signals) == 1
    sig = signals[0]
    assert sig.entry_price == 80
    # 2 bars after the cliff: 80 -> 88 = +10%.
    assert sig.forward_return == pytest.approx(88 / 80 - 1)
    assert sig.drawdown == pytest.approx(80 / 100 - 1)


def test_positions_are_non_overlapping() -> None:
    # A long depressed run: many bars sit below the window high, but entries must
    # be spaced by the horizon, not one per bar.
    closes = [100, 100, 100, 100, 100] + [80] * 12
    signals, _ = find_rebound_signals(
        _series(closes), threshold=-0.15, window=5, horizon=3, min_points=3
    )
    dates = [s.signal_date for s in signals]
    # Consecutive entries are >= horizon days apart.
    assert all((b - a).days >= 3 for a, b in zip(dates, dates[1:], strict=False))


def test_missing_forward_bar_counted_as_dropped() -> None:
    # Drop at the very end: no bar `horizon` ahead to score it.
    closes = [100, 110, 120, 118, 110, 100, 90]
    signals, dropped = find_rebound_signals(
        _series(closes), threshold=-0.15, window=6, horizon=5, min_points=3
    )
    assert signals == []
    assert dropped == 1


def test_large_calendar_gap_forward_bar_dropped() -> None:
    # Flat 100 then a cliff to 80 (entry), whose only forward bar is ~6 months
    # later (sparse, event-window-only history) -> no clean horizon return.
    pts = [
        PricePoint(date=date(2026, 1, 1), adj_close=100),
        PricePoint(date=date(2026, 1, 2), adj_close=100),
        PricePoint(date=date(2026, 1, 3), adj_close=100),
        PricePoint(date=date(2026, 1, 4), adj_close=100),
        PricePoint(date=date(2026, 1, 5), adj_close=80),  # -20% drop, entry here
        PricePoint(date=date(2026, 7, 20), adj_close=90),  # forward bar, huge gap
    ]
    signals, dropped = find_rebound_signals(
        pts, threshold=-0.15, window=4, horizon=1, min_points=3
    )
    assert signals == []
    assert dropped == 1


def test_aggregate_raw_hit_rate_and_costs() -> None:
    # Two instruments, each a clean cliff: one rebounds (+10%), one falls (-10%).
    up = [100.0] * 12 + [80, 88]
    down = [100.0] * 12 + [80, 72]
    result = rebound_backtest(
        {1: _series(up), 2: _series(down)},
        horizon=1,
        threshold=-0.15,
        window=12,
        min_points=5,
        commission_per_trade=0.001,
        slippage_per_trade=0.001,
    )
    assert result.market_adjusted is False
    assert result.n_signals == 2
    assert result.hit_rate == pytest.approx(0.5)  # one up, one down
    assert result.mean_forward_return == pytest.approx(0.0)  # +10% and -10%
    assert result.mean_forward_return_net == pytest.approx(
        result.mean_forward_return - 0.002
    )


def test_aggregate_market_adjustment_with_benchmark() -> None:
    closes = [100.0] * 12 + [80, 88]  # clean cliff, entry 80 -> forward 88 (+10% raw)
    # Benchmark rises every day, so its return over the position is > 0 and the
    # abnormal (market-adjusted) forward return is below the raw one.
    bench = _series([100.0 + i for i in range(15)])
    result = rebound_backtest(
        {1: _series(closes)},
        horizon=1,
        threshold=-0.15,
        window=12,
        min_points=5,
        benchmark_by_market={"US": bench},
        instrument_market={1: "US"},
    )
    assert result.market_adjusted is True
    assert result.n_signals == 1
    assert result.mean_abnormal_return is not None
    assert result.mean_abnormal_return < result.mean_forward_return


def test_empty_input_is_safe() -> None:
    result = rebound_backtest({}, horizon=5)
    assert result.n_signals == 0
    assert result.hit_rate is None
    assert result.mean_forward_return is None
