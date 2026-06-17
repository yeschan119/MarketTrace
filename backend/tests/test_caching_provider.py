"""Tests for CachingPriceProvider: fetch-once-per-ticker + correct slicing."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from markettrace.providers.caching import CachingPriceProvider


class _FakeProvider:
    """Records every call and returns one row per calendar day in the range."""

    market = "US"

    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date]] = []

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        self.calls.append((ticker, start, end))
        days = (end - start).days + 1
        dates = [start + timedelta(days=i) for i in range(days)]
        return pl.DataFrame({"date": dates, "close": [float(i) for i in range(days)]})


def test_market_is_delegated() -> None:
    assert CachingPriceProvider(_FakeProvider()).market == "US"


def test_overlapping_requests_fetch_once() -> None:
    inner = _FakeProvider()
    provider = CachingPriceProvider(inner)

    a = provider.get_ohlcv("GOOGL", date(2026, 5, 16), date(2026, 10, 3))
    b = provider.get_ohlcv("GOOGL", date(2026, 5, 6), date(2026, 9, 23))
    c = provider.get_ohlcv("GOOGL", date(2026, 1, 1), date(2026, 3, 1))

    # All three windows fall within the first padded fetch -> exactly one call.
    assert len(inner.calls) == 1
    # Each call returns rows bounded by its own requested window.
    assert a["date"].min() >= date(2026, 5, 16)
    assert a["date"].max() <= date(2026, 10, 3)
    assert b["date"].min() >= date(2026, 5, 6)
    assert c["date"].max() <= date(2026, 3, 1)


def test_repeated_index_fetch_is_cached_across_tickers() -> None:
    inner = _FakeProvider()
    provider = CachingPriceProvider(inner)

    # Simulate the market index being requested once per filing.
    for _ in range(50):
        provider.get_ohlcv("SPY", date(2026, 6, 1), date(2026, 8, 1))

    assert len(inner.calls) == 1  # 50 requests -> a single upstream fetch


def test_slice_matches_direct_fetch() -> None:
    inner = _FakeProvider()
    provider = CachingPriceProvider(inner, pad=timedelta(0))

    direct = _FakeProvider().get_ohlcv("AAPL", date(2026, 6, 1), date(2026, 6, 10))
    cached = provider.get_ohlcv("AAPL", date(2026, 6, 1), date(2026, 6, 10))
    assert cached["date"].to_list() == direct["date"].to_list()


def test_request_outside_cached_range_refetches() -> None:
    inner = _FakeProvider()
    provider = CachingPriceProvider(inner, pad=timedelta(0))  # exact coverage

    provider.get_ohlcv("AAPL", date(2026, 6, 1), date(2026, 6, 10))
    provider.get_ohlcv("AAPL", date(2026, 6, 1), date(2026, 6, 10))  # covered -> cache hit
    provider.get_ohlcv("AAPL", date(2025, 1, 1), date(2025, 1, 10))  # earlier -> miss

    assert len(inner.calls) == 2


def test_distinct_tickers_cached_separately() -> None:
    inner = _FakeProvider()
    provider = CachingPriceProvider(inner)

    provider.get_ohlcv("AAPL", date(2026, 6, 1), date(2026, 6, 10))
    provider.get_ohlcv("MSFT", date(2026, 6, 1), date(2026, 6, 10))

    assert {c[0] for c in inner.calls} == {"AAPL", "MSFT"}
    assert len(inner.calls) == 2
