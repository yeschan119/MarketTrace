"""Stooq daily OHLCV price provider.

Downloads CSV data from stooq.com for US-listed tickers.  Network access is
injectable via ``httpx.Client`` so tests can supply a mock transport.

Note: Stooq does not publish a separate adjusted-close column; ``adj_close``
is set equal to ``close`` as documented by stooq's CSV format.
"""

from __future__ import annotations

import io
from datetime import date

import httpx
import polars as pl

from markettrace.providers.base import PriceProvider

__all__ = ["StooqPriceProvider"]

_STOOQ_URL = (
    "https://stooq.com/q/d/l/?s={ticker}.us&d1={start}&d2={end}&i=d"
)


class StooqPriceProvider:
    """``PriceProvider`` backed by stooq.com daily CSV downloads."""

    market: str = "US"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client()

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        """Return a polars DataFrame with daily OHLCV data sorted ascending.

        Columns
        -------
        date     : pl.Date
        open     : pl.Float64
        high     : pl.Float64
        low      : pl.Float64
        close    : pl.Float64
        adj_close: pl.Float64  (equals close — stooq has no separate adj col)
        volume   : pl.Float64
        """
        url = _STOOQ_URL.format(
            ticker=ticker.lower(),
            start=start.strftime("%Y%m%d"),
            end=end.strftime("%Y%m%d"),
        )
        resp = self._client.get(url)
        resp.raise_for_status()

        raw = pl.read_csv(
            io.StringIO(resp.text),
            schema_overrides={
                "Date": pl.Utf8,
                "Open": pl.Float64,
                "High": pl.Float64,
                "Low": pl.Float64,
                "Close": pl.Float64,
                "Volume": pl.Float64,
            },
        )

        df = (
            raw.rename(
                {
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            .with_columns(
                pl.col("date").str.to_date("%Y-%m-%d"),
                pl.col("close").alias("adj_close"),  # stooq has no separate adj
            )
            .select(["date", "open", "high", "low", "close", "adj_close", "volume"])
            .sort("date")
        )

        return df


# Satisfy the Protocol at import-time.
_: PriceProvider = StooqPriceProvider.__new__(StooqPriceProvider)  # type: ignore[assignment]
