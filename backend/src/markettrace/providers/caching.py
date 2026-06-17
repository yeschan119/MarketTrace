"""Caching wrapper that coalesces redundant OHLCV fetches during ingestion.

Corpus ingestion re-fetches the same tickers' prices relentlessly: the market
index for *every* filing, and each stock across ~10 overlapping event windows.
On a rate-limited free tier (Tiingo returns 429 once its hourly quota is spent)
this exhausts the quota almost immediately — retrying with backoff can't beat a
hard quota, only fewer requests can.

This wrapper fetches a deliberately *wide* window per ticker ONCE and serves
every later request from memory, turning ~1000 calls into roughly one per
distinct ticker (~20 stocks + the index + a handful of sector ETFs). Slicing a
wide fetch is identical to issuing a narrow query — daily OHLCV for a given date
does not depend on the request's date range — so results are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl

from markettrace.providers.base import PriceProvider

__all__ = ["CachingPriceProvider"]

# Pad each fetch generously so a ticker's other event windows (and the +60-day
# outcome horizon) fall inside the single cached fetch regardless of the order
# requests arrive in. ~900 days covers the corpus span in both directions.
_DEFAULT_PAD = timedelta(days=900)


@dataclass
class _Entry:
    start: date
    end: date
    df: pl.DataFrame


class CachingPriceProvider:
    """Wrap a ``PriceProvider``, caching one wide fetch per ticker."""

    def __init__(self, inner: PriceProvider, *, pad: timedelta = _DEFAULT_PAD) -> None:
        self._inner = inner
        self._pad = pad
        self._cache: dict[str, _Entry] = {}

    @property
    def market(self) -> str:
        return self._inner.market

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        key = ticker.lower()
        entry = self._cache.get(key)
        if entry is None or start < entry.start or end > entry.end:
            # Miss (or partial coverage): fetch the union of the requested and
            # any previously-cached range, padded, so future nearby requests hit.
            fetch_start = (min(start, entry.start) if entry else start) - self._pad
            fetch_end = (max(end, entry.end) if entry else end) + self._pad
            df = self._inner.get_ohlcv(ticker, fetch_start, fetch_end)
            entry = _Entry(fetch_start, fetch_end, df)
            self._cache[key] = entry
        return entry.df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
