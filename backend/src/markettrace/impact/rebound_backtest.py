"""Mean-reversion rebound backtest — validates the "overreaction" claim (Feature 1, stage 4).

The drop screener flags sharply-fallen names ``possible_overreaction`` as a
*rebound candidate*, but the app must not present that as a signal until it is
validated out of sample (blueprint §9: no claim without measurement). This module
tests the underlying hypothesis directly and honestly:

    After a stock falls at least `threshold` from its trailing `window`-day high,
    is its forward return over the next `horizon` trading days positive — net of
    trading costs, and in excess of the market?

It is look-ahead-safe by construction: the fixed rule "buy after an X% drop" is
specified a priori, never fit to the data, so every signal is genuinely
out-of-sample. The entry decision at day ``t`` reads only prices up to ``t``; the
outcome reads ``t → t+horizon`` (the realised future), which is measured, not used
to decide. Positions are **non-overlapping** (a new signal for an instrument only
after the prior position's horizon elapses) so nearby days of the same drawdown
don't inflate the sample with near-duplicate outcomes.

Coverage is reported honestly: a signal whose forward bar is missing or separated
from entry by a large calendar gap (sparse, event-window-only price history) has
no clean horizon return and is counted in ``n_dropped_no_outcome`` rather than
silently dropped. With the current sparse prices this count can dominate — that
is the true state, and hiding it would fabricate an edge.

Pure functions over price series (trivially testable); a thin session helper
pulls per-instrument series and the market benchmark from the ``prices`` table.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import Instrument, Price
from markettrace.impact.drawdown import DEFAULT_WINDOW, MIN_POINTS, PricePoint, compute_drawdown

__all__ = [
    "DEFAULT_THRESHOLD",
    "ReboundSignal",
    "ReboundBacktestResult",
    "find_rebound_signals",
    "rebound_backtest",
    "run_rebound_backtest",
]

# A signal fires when the trailing-window drawdown is at or below this (<= 0).
DEFAULT_THRESHOLD = -0.15

# Max calendar days a forward bar may sit past entry before we consider the
# horizon return un-measurable (a gap in sparse, event-window-only history).
_MAX_FORWARD_GAP_DAYS = 15


@dataclass(frozen=True)
class ReboundSignal:
    """One drop entry and its realised raw forward return over the horizon."""

    signal_date: date
    drawdown: float
    entry_price: float
    forward_date: date
    forward_return: float  # raw: exit/entry - 1


@dataclass(frozen=True)
class ReboundBacktestResult:
    """Out-of-sample summary of the drop -> forward-return rule at one horizon."""

    horizon_days: int
    threshold: float
    window: int
    n_signals_total: int  # all drop entries detected (incl. missing outcomes)
    n_dropped_no_outcome: int  # entries with no clean forward bar
    n_signals: int  # entries with a usable forward return
    hit_rate: float | None  # fraction with positive (adjusted, if available) return
    mean_forward_return: float | None  # raw, gross
    mean_forward_return_net: float | None  # raw, minus round-trip cost
    mean_abnormal_return: float | None  # market-adjusted, gross (None w/o benchmark)
    mean_abnormal_return_net: float | None
    market_adjusted: bool
    commission_per_trade: float
    slippage_per_trade: float


def find_rebound_signals(
    prices: list[PricePoint],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    window: int = DEFAULT_WINDOW,
    horizon: int,
    min_points: int = MIN_POINTS,
) -> tuple[list[ReboundSignal], int]:
    """Detect non-overlapping drop entries in one instrument's price series.

    Walks the (date-sorted) series; at each bar computes the trailing-``window``
    drawdown and, when it is at or below ``threshold``, records an entry whose
    outcome is the raw return to the bar ``horizon`` positions later. After a
    qualifying drop the next candidate is skipped forward by ``horizon`` bars so
    positions never overlap. A qualifying drop whose forward bar is missing, or
    separated from entry by more than a horizon-sized calendar gap, is *not*
    scored but *is* counted — the function returns ``(scored_signals,
    n_dropped_no_outcome)`` so sparse-data coverage stays visible upstream.
    """
    if horizon < 1 or not prices:
        return [], 0

    ordered = sorted(prices, key=lambda p: p.date)
    n = len(ordered)
    signals: list[ReboundSignal] = []
    n_dropped = 0

    i = 0
    while i < n:
        window_slice = ordered[max(0, i - window + 1) : i + 1]
        result = compute_drawdown(window_slice, window=window, min_points=min_points)
        if result is None or result.drawdown > threshold:
            i += 1
            continue

        entry = ordered[i]
        forward_idx = i + horizon
        exit_bar = ordered[forward_idx] if forward_idx < n else None
        gap_ok = (
            exit_bar is not None
            and (exit_bar.date - entry.date).days <= horizon + _MAX_FORWARD_GAP_DAYS
        )
        if exit_bar is not None and gap_ok and entry.adj_close > 0:
            signals.append(
                ReboundSignal(
                    signal_date=entry.date,
                    drawdown=result.drawdown,
                    entry_price=entry.adj_close,
                    forward_date=exit_bar.date,
                    forward_return=exit_bar.adj_close / entry.adj_close - 1.0,
                )
            )
        else:
            n_dropped += 1
        # Non-overlapping: jump past this position's horizon regardless of outcome.
        i += horizon

    return signals, n_dropped


def _benchmark_return(
    benchmark: list[PricePoint] | None, start: date, end: date
) -> float | None:
    """Raw benchmark return between ``start`` and ``end`` using last bar <= each date."""
    if not benchmark:
        return None
    dates = [p.date for p in benchmark]
    vals = [p.adj_close for p in benchmark]

    def _at(d: date) -> float | None:
        idx = bisect.bisect_right(dates, d) - 1
        return vals[idx] if idx >= 0 else None

    start_px = _at(start)
    end_px = _at(end)
    if start_px is None or end_px is None or start_px <= 0:
        return None
    return end_px / start_px - 1.0


def rebound_backtest(
    series_by_instrument: dict[int, list[PricePoint]],
    *,
    horizon: int,
    threshold: float = DEFAULT_THRESHOLD,
    window: int = DEFAULT_WINDOW,
    min_points: int = MIN_POINTS,
    benchmark_by_market: dict[str, list[PricePoint]] | None = None,
    instrument_market: dict[int, str] | None = None,
    commission_per_trade: float = 0.0,
    slippage_per_trade: float = 0.0,
) -> ReboundBacktestResult:
    """Aggregate the drop -> forward-return rule across instruments at one horizon.

    Each instrument's non-overlapping drop entries are pooled. When a benchmark
    series is available for the instrument's market, the entry's market-adjusted
    (abnormal) forward return is the raw forward return minus the benchmark's
    return over the same dates; ``hit_rate`` is then computed on the abnormal
    return (else on the raw return). ``n_dropped_no_outcome`` counts entries with
    no clean forward bar so sparse-data coverage stays visible.
    """
    benchmark_by_market = benchmark_by_market or {}
    instrument_market = instrument_market or {}

    raw_returns: list[float] = []
    abnormal_returns: list[float] = []
    n_dropped = 0

    for instrument_id, prices in series_by_instrument.items():
        signals, dropped = find_rebound_signals(
            prices,
            threshold=threshold,
            window=window,
            horizon=horizon,
            min_points=min_points,
        )
        n_dropped += dropped
        market = instrument_market.get(instrument_id)
        benchmark = benchmark_by_market.get(market) if market else None
        for sig in signals:
            raw_returns.append(sig.forward_return)
            bench = _benchmark_return(benchmark, sig.signal_date, sig.forward_date)
            if bench is not None:
                abnormal_returns.append(sig.forward_return - bench)

    market_adjusted = len(abnormal_returns) == len(raw_returns) and bool(raw_returns)
    round_trip = commission_per_trade + slippage_per_trade

    def _mean(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    # Hit rate and the headline are on abnormal returns when we could adjust every
    # signal; otherwise on raw returns (partial adjustment would mix bases).
    scored = abnormal_returns if market_adjusted else raw_returns
    hit_rate = (
        sum(1 for r in scored if r > 0) / len(scored) if scored else None
    )

    mean_raw = _mean(raw_returns)
    mean_abn = _mean(abnormal_returns) if market_adjusted else None

    return ReboundBacktestResult(
        horizon_days=horizon,
        threshold=threshold,
        window=window,
        n_signals_total=len(raw_returns) + n_dropped,
        n_dropped_no_outcome=n_dropped,
        n_signals=len(raw_returns),
        hit_rate=hit_rate,
        mean_forward_return=mean_raw,
        mean_forward_return_net=(mean_raw - round_trip) if mean_raw is not None else None,
        mean_abnormal_return=mean_abn,
        mean_abnormal_return_net=(mean_abn - round_trip) if mean_abn is not None else None,
        market_adjusted=market_adjusted,
        commission_per_trade=commission_per_trade,
        slippage_per_trade=slippage_per_trade,
    )


def run_rebound_backtest(
    session: Session,
    *,
    horizons: Iterable[int],
    benchmark_tickers: Mapping[str, str],
    threshold: float = DEFAULT_THRESHOLD,
    window: int = DEFAULT_WINDOW,
    commission_per_trade: float = 0.0,
    slippage_per_trade: float = 0.0,
) -> list[ReboundBacktestResult]:
    """Backtest the drop->rebound rule from stored prices, one result per horizon.

    Loads every instrument's adjusted-close series from ``prices``. The benchmark
    instrument for each market (``benchmark_tickers`` maps e.g. ``"US" -> "SPY"``)
    is pulled out as the market-adjustment series and excluded from the tested
    universe. When a market's benchmark is present, that market's signals are
    market-adjusted; otherwise the result reports raw returns
    (``market_adjusted=False``). Prices here come from
    ``markettrace-refresh-prices`` — with only sparse event-window history the
    ``n_dropped_no_outcome`` coverage figure will be large, which is the honest
    state, not an edge.
    """
    series: dict[int, list[PricePoint]] = {}
    for iid, pdate, px in session.execute(
        select(Price.instrument_id, Price.date, Price.adj_close).order_by(
            Price.instrument_id, Price.date
        )
    ).all():
        series.setdefault(iid, []).append(PricePoint(date=pdate, adj_close=px))

    instrument_market: dict[int, str] = {}
    benchmark_ids: set[int] = set()
    benchmark_by_market: dict[str, list[PricePoint]] = {}
    for iid, market, ticker in session.execute(
        select(Instrument.id, Instrument.market, Instrument.ticker)
    ).all():
        instrument_market[iid] = market
        if benchmark_tickers.get(market) == ticker:
            benchmark_ids.add(iid)
            if iid in series:
                benchmark_by_market[market] = series[iid]

    tested = {iid: s for iid, s in series.items() if iid not in benchmark_ids}

    return [
        rebound_backtest(
            tested,
            horizon=horizon,
            threshold=threshold,
            window=window,
            benchmark_by_market=benchmark_by_market,
            instrument_market=instrument_market,
            commission_per_trade=commission_per_trade,
            slippage_per_trade=slippage_per_trade,
        )
        for horizon in horizons
    ]
