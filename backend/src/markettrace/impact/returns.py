"""Cumulative return and event-outcome computation.

Trading-day semantics
---------------------
All horizon offsets are *positional* — they count rows in the sorted price
DataFrame, not calendar days.  A horizon of 5 means "the close price 5 trading
days after the event close", regardless of weekends or holidays.  This avoids
look-ahead bias from calendar arithmetic and matches how event-study literature
defines post-announcement windows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

from markettrace.impact import market_model


@dataclass(frozen=True)
class OutcomeResult:
    """Per-horizon outcome metrics for a single event.

    Attributes
    ----------
    horizon_days:
        Number of trading days after the event date used as the exit point.
    raw_return:
        Cumulative simple return of the stock over ``horizon_days`` trading
        days, or ``None`` if data is unavailable.
    market_return:
        Cumulative simple return of the benchmark index over the same window,
        or ``None`` if data is unavailable.
    abnormal_return:
        ``raw_return - market_return`` (market-adjusted model, beta = 1).
        ``None`` when either component is ``None``.
    """

    horizon_days: int
    raw_return: float | None
    market_return: float | None
    abnormal_return: float | None


def cumulative_return(
    prices: pl.DataFrame,
    t0: date,
    horizon: int,
    price_col: str = "adj_close",
) -> float | None:
    """Compute the cumulative simple return over *horizon* trading days.

    Parameters
    ----------
    prices:
        DataFrame with at least two columns: ``date`` (``pl.Date``) and
        *price_col* (numeric).  Must be sorted ascending by date.
    t0:
        The event close date used as the baseline (index row ``idx``).
        The return is ``price[idx + horizon] / price[idx] - 1``.
    horizon:
        Number of trading-day rows to look forward from ``t0``.
    price_col:
        Name of the price column to use (default ``"adj_close"``).

    Returns
    -------
    float | None
        The cumulative simple return, or ``None`` if ``t0`` is not present in
        *prices* or ``idx + horizon`` is out of range.
    """
    date_series: pl.Series = prices["date"]

    # Find the positional index of t0 in the date column.
    mask: pl.Series = date_series == t0
    matching_indices = mask.arg_true()  # indices where condition holds

    if len(matching_indices) == 0:
        return None

    idx: int = int(matching_indices[0])
    target_idx: int = idx + horizon

    if target_idx >= len(prices):
        return None

    price_series: pl.Series = prices[price_col]
    p0: float = float(price_series[idx])
    p1: float = float(price_series[target_idx])

    if p0 == 0.0:
        return None

    return p1 / p0 - 1.0


def compute_event_outcomes(
    stock_prices: pl.DataFrame,
    market_prices: pl.DataFrame,
    event_date: date,
    horizons: tuple[int, ...] = (1, 5, 20),
    price_col: str = "adj_close",
) -> list[OutcomeResult]:
    """Compute market-adjusted abnormal returns for each horizon.

    For each horizon ``h`` in *horizons*:

    1. ``raw_return`` = cumulative return of *stock_prices* over ``h`` trading
       days starting from *event_date*.
    2. ``market_return`` = same calculation on *market_prices*.
    3. ``abnormal_return`` = ``raw_return - market_return`` (market-adjusted
       model).  If either component is ``None``, ``abnormal_return`` is also
       ``None``.

    Parameters
    ----------
    stock_prices:
        Price DataFrame for the stock instrument.
    market_prices:
        Price DataFrame for the benchmark index.
    event_date:
        The event close date (baseline row ``t0``).
    horizons:
        Tuple of trading-day horizons to evaluate (default ``(1, 5, 20)``).
    price_col:
        Price column name used in both DataFrames (default ``"adj_close"``).

    Returns
    -------
    list[OutcomeResult]
        One ``OutcomeResult`` per horizon, in the same order as *horizons*.
    """
    results: list[OutcomeResult] = []

    for h in horizons:
        raw = cumulative_return(stock_prices, event_date, h, price_col)
        mkt = cumulative_return(market_prices, event_date, h, price_col)

        if raw is None or mkt is None:
            ar: float | None = None
        else:
            ar = market_model.abnormal_return(raw, mkt)

        results.append(
            OutcomeResult(
                horizon_days=h,
                raw_return=raw,
                market_return=mkt,
                abnormal_return=ar,
            )
        )

    return results
