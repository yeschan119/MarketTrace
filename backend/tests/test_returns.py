"""Tests for impact.returns and impact.market_model.

Trading-day semantics: all horizon offsets are positional row counts in the
sorted price DataFrame, not calendar days.

Synthetic data design
---------------------
We build a 30-row price series (trading days 0..29) with a known event on
row 10 (date 2024-01-15).  Prices are chosen so that exact integer arithmetic
holds:

  stock adj_close:
    row 10  (t0)        : 100.0
    row 11  (t0 + 1)    : 102.0   -> 1d raw = 102/100 - 1 =  0.02
    row 15  (t0 + 5)    : 110.0   -> 5d raw = 110/100 - 1 =  0.10
    row 30  would be OOB (only 30 rows, indices 0-29; t0+20 = row 30 = OOB)
    row 29  (t0 + 19)   : exists but t0+20 is not
    -> to make 20d work we place t0 at row 5 in a 30-row frame (see below)

Re-design for all three horizons to be in range:
  Frame: 30 rows, indices 0..29.  Event at row 5 (date index_to_date(5)).
  t0 + 1  = row 6
  t0 + 5  = row 10
  t0 + 20 = row 25   <- still in range (< 30)

Stock prices (adj_close):
  row 5  : 100.0
  row 6  : 103.0   -> 1d raw  = 0.03
  row 10 : 115.0   -> 5d raw  = 0.15
  row 25 : 140.0   -> 20d raw = 0.40

Market prices (adj_close):
  row 5  : 200.0
  row 6  : 202.0   -> 1d mkt  = 0.01
  row 10 : 210.0   -> 5d mkt  = 0.05
  row 25 : 220.0   -> 20d mkt = 0.10

Expected abnormal returns:
  1d  : 0.03 - 0.01 = 0.02
  5d  : 0.15 - 0.05 = 0.10
  20d : 0.40 - 0.10 = 0.30

All other rows use a linear interpolation that doesn't matter for these tests.
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from markettrace.impact.market_model import abnormal_return
from markettrace.impact.returns import OutcomeResult, compute_event_outcomes, cumulative_return

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_DATE = date(2024, 1, 2)  # a Tuesday; we treat every row as a trading day


def _make_date(row_index: int) -> date:
    """Map a row index to a calendar date (one day per row, ignores weekends)."""
    return _BASE_DATE + timedelta(days=row_index)


def _build_stock_prices() -> pl.DataFrame:
    """30-row stock price frame with controlled adj_close values."""
    n = 30
    # Default adj_close = 50.0; override at key rows.
    adj_closes = [50.0] * n
    adj_closes[5] = 100.0
    adj_closes[6] = 103.0
    adj_closes[10] = 115.0
    adj_closes[25] = 140.0

    dates = [_make_date(i) for i in range(n)]
    return pl.DataFrame({"date": dates, "adj_close": adj_closes})


def _build_market_prices() -> pl.DataFrame:
    """30-row market index frame with controlled adj_close values."""
    n = 30
    adj_closes = [150.0] * n
    adj_closes[5] = 200.0
    adj_closes[6] = 202.0
    adj_closes[10] = 210.0
    adj_closes[25] = 220.0

    dates = [_make_date(i) for i in range(n)]
    return pl.DataFrame({"date": dates, "adj_close": adj_closes})


_EVENT_DATE = _make_date(5)  # row 5
_STOCK = _build_stock_prices()
_MARKET = _build_market_prices()


# ---------------------------------------------------------------------------
# market_model tests
# ---------------------------------------------------------------------------


def test_abnormal_return_positive_outperformance() -> None:
    assert abnormal_return(0.05, 0.02) == pytest.approx(0.03)


def test_abnormal_return_underperformance() -> None:
    assert abnormal_return(0.01, 0.04) == pytest.approx(-0.03)


def test_abnormal_return_neutral() -> None:
    assert abnormal_return(0.07, 0.07) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# cumulative_return tests
# ---------------------------------------------------------------------------


def test_cumulative_return_1d() -> None:
    result = cumulative_return(_STOCK, _EVENT_DATE, horizon=1)
    # 103.0 / 100.0 - 1 = 0.03
    assert result == pytest.approx(0.03)


def test_cumulative_return_5d() -> None:
    result = cumulative_return(_STOCK, _EVENT_DATE, horizon=5)
    # 115.0 / 100.0 - 1 = 0.15
    assert result == pytest.approx(0.15)


def test_cumulative_return_20d() -> None:
    result = cumulative_return(_STOCK, _EVENT_DATE, horizon=20)
    # 140.0 / 100.0 - 1 = 0.40
    assert result == pytest.approx(0.40)


def test_cumulative_return_out_of_range_returns_none() -> None:
    """horizon=25 from row 5 -> row 30, which is out of bounds (max index 29)."""
    result = cumulative_return(_STOCK, _EVENT_DATE, horizon=25)
    assert result is None


def test_cumulative_return_missing_event_date_returns_none() -> None:
    """A date not present in the frame must return None."""
    absent_date = date(2099, 1, 1)
    result = cumulative_return(_STOCK, absent_date, horizon=1)
    assert result is None


def test_cumulative_return_custom_price_col() -> None:
    """cumulative_return respects the price_col parameter."""
    df = pl.DataFrame(
        {
            "date": [_BASE_DATE, _BASE_DATE + timedelta(days=1)],
            "close": [50.0, 55.0],
        }
    )
    result = cumulative_return(df, _BASE_DATE, horizon=1, price_col="close")
    assert result == pytest.approx(0.10)


def test_cumulative_return_horizon_zero() -> None:
    """horizon=0 means entry and exit are the same row -> return = 0.0."""
    result = cumulative_return(_STOCK, _EVENT_DATE, horizon=0)
    assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_event_outcomes tests
# ---------------------------------------------------------------------------


def test_compute_event_outcomes_returns_one_per_horizon() -> None:
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE, horizons=(1, 5, 20))
    assert len(outcomes) == 3
    assert all(isinstance(o, OutcomeResult) for o in outcomes)


def test_compute_event_outcomes_horizon_order_preserved() -> None:
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE, horizons=(1, 5, 20))
    assert [o.horizon_days for o in outcomes] == [1, 5, 20]


def test_compute_event_outcomes_1d_values() -> None:
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE, horizons=(1,))
    o = outcomes[0]
    assert o.horizon_days == 1
    assert o.raw_return == pytest.approx(0.03)
    assert o.market_return == pytest.approx(0.01)
    assert o.abnormal_return == pytest.approx(0.02)


def test_compute_event_outcomes_5d_values() -> None:
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE, horizons=(5,))
    o = outcomes[0]
    assert o.horizon_days == 5
    assert o.raw_return == pytest.approx(0.15)
    assert o.market_return == pytest.approx(0.05)
    assert o.abnormal_return == pytest.approx(0.10)


def test_compute_event_outcomes_20d_values() -> None:
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE, horizons=(20,))
    o = outcomes[0]
    assert o.horizon_days == 20
    assert o.raw_return == pytest.approx(0.40)
    assert o.market_return == pytest.approx(0.10)
    assert o.abnormal_return == pytest.approx(0.30)


def test_compute_event_outcomes_out_of_range_horizon_is_none() -> None:
    """horizon=25 from row 5 is out of range -> all fields None."""
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE, horizons=(25,))
    o = outcomes[0]
    assert o.horizon_days == 25
    assert o.raw_return is None
    assert o.market_return is None
    assert o.abnormal_return is None


def test_compute_event_outcomes_missing_event_date_is_none() -> None:
    """When event_date is absent from stock frame, every field must be None."""
    absent = date(2099, 1, 1)
    outcomes = compute_event_outcomes(_STOCK, _MARKET, absent, horizons=(1, 5, 20))
    for o in outcomes:
        assert o.raw_return is None
        assert o.market_return is None
        assert o.abnormal_return is None


def test_compute_event_outcomes_partial_none_propagates() -> None:
    """If only market data is missing for a horizon, abnormal_return is None."""
    # Build a market frame that has the event date but only 6 rows (no row 10 or 25).
    small_market = pl.DataFrame(
        {
            "date": [_make_date(i) for i in range(6)],
            "adj_close": [200.0, 201.0, 202.0, 203.0, 204.0, 205.0],
        }
    )
    # horizon=1: market row 6 doesn't exist -> market_return None -> AR None
    outcomes = compute_event_outcomes(_STOCK, small_market, _EVENT_DATE, horizons=(1,))
    o = outcomes[0]
    assert o.raw_return == pytest.approx(0.03)   # stock data is fine
    assert o.market_return is None
    assert o.abnormal_return is None


def test_outcome_result_is_frozen() -> None:
    """OutcomeResult must be immutable (frozen dataclass)."""
    o = OutcomeResult(horizon_days=1, raw_return=0.03, market_return=0.01, abnormal_return=0.02)
    with pytest.raises((AttributeError, TypeError)):
        o.raw_return = 0.99  # type: ignore[misc]


def test_compute_event_outcomes_default_horizons() -> None:
    """Default horizons are (1, 5, 20, 60)."""
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE)
    assert [o.horizon_days for o in outcomes] == [1, 5, 20, 60]


def test_compute_event_outcomes_60d_out_of_range_is_none() -> None:
    """The 30-row synthetic frame cannot reach a 60-day horizon -> None fields."""
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE, horizons=(60,))
    o = outcomes[0]
    assert o.horizon_days == 60
    assert o.raw_return is None
    assert o.abnormal_return is None


def test_compute_event_outcomes_sector_none_by_default() -> None:
    """Without sector_prices, sector fields stay None."""
    outcomes = compute_event_outcomes(_STOCK, _MARKET, _EVENT_DATE, horizons=(1,))
    o = outcomes[0]
    assert o.sector_return is None
    assert o.sector_abnormal_return is None


def test_compute_event_outcomes_sector_adjusted_values() -> None:
    """With a sector frame, sector_abnormal_return = raw - sector."""
    # Sector index: row 5 -> 300.0, row 6 -> 306.0  => 1d sector return = 0.02
    n = 30
    sector_closes = [250.0] * n
    sector_closes[5] = 300.0
    sector_closes[6] = 306.0
    sector_df = pl.DataFrame(
        {"date": [_make_date(i) for i in range(n)], "adj_close": sector_closes}
    )
    outcomes = compute_event_outcomes(
        _STOCK, _MARKET, _EVENT_DATE, horizons=(1,), sector_prices=sector_df
    )
    o = outcomes[0]
    # raw 1d = 0.03, sector 1d = 0.02  => sector abnormal = 0.01
    assert o.raw_return == pytest.approx(0.03)
    assert o.sector_return == pytest.approx(0.02)
    assert o.sector_abnormal_return == pytest.approx(0.01)
    # market-adjusted figure is unchanged by the sector input
    assert o.abnormal_return == pytest.approx(0.02)
