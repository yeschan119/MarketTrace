"""Tiingo daily OHLCV price provider.

Downloads end-of-day price data from the Tiingo REST API for US-listed
tickers.  Network access is injectable via ``httpx.Client`` so tests can supply
a mock transport.

Unlike Stooq, Tiingo publishes a genuine split/dividend-adjusted close
(``adjClose``), which is mapped to the ``adj_close`` column.
"""

from __future__ import annotations

from datetime import date

import httpx
import polars as pl

from markettrace.providers.base import PriceProvider

__all__ = ["TiingoPriceProvider"]

_TIINGO_URL = "https://api.tiingo.com/tiingo/daily/{ticker}/prices"


class TiingoPriceProvider:
    """``PriceProvider`` backed by the Tiingo daily-prices REST API."""

    market: str = "US"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
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
        adj_close: pl.Float64  (Tiingo ``adjClose`` — split/dividend adjusted)
        volume   : pl.Float64
        """
        url = _TIINGO_URL.format(ticker=ticker.lower())
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Token {self._api_key}"

        resp = self._client.get(
            url,
            params={
                "startDate": start.strftime("%Y-%m-%d"),
                "endDate": end.strftime("%Y-%m-%d"),
                "format": "json",
            },
            headers=headers,
        )
        resp.raise_for_status()

        rows = resp.json()
        raw = pl.DataFrame(
            rows,
            schema_overrides={
                "date": pl.Utf8,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "adjClose": pl.Float64,
                "volume": pl.Float64,
            },
        )

        df = (
            raw.with_columns(
                # Tiingo dates are ISO timestamps (e.g. "2024-05-15T00:00:00.000Z");
                # keep only the calendar date.
                pl.col("date").str.slice(0, 10).str.to_date("%Y-%m-%d"),
            )
            .rename({"adjClose": "adj_close"})
            .select(["date", "open", "high", "low", "close", "adj_close", "volume"])
            .sort("date")
        )

        return df


# Satisfy the Protocol at import-time.
_: PriceProvider = TiingoPriceProvider.__new__(TiingoPriceProvider)  # type: ignore[assignment]
