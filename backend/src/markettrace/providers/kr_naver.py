"""Naver Finance daily OHLCV price provider (KR market).

Downloads end-of-day price data from Naver Finance's ``siseJson`` endpoint for
KR-listed tickers (6-digit codes, e.g. ``005930``).  Network access is
injectable via ``httpx.Client`` so tests can supply a mock transport.

The endpoint returns a *Python-literal* array (single + double quotes, tabs and
newlines) rather than JSON, so the body is parsed with ``ast.literal_eval``.
Naver does not publish a separate adjusted-close column; ``adj_close`` is set
equal to ``close`` (mirroring the Stooq provider).
"""

from __future__ import annotations

import ast
from datetime import date

import httpx
import polars as pl

from markettrace.providers.base import PriceProvider

__all__ = ["KrNaverPriceProvider"]

_NAVER_URL = "https://api.finance.naver.com/siseJson.naver"

_OUTPUT_COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume"]

_EMPTY_SCHEMA = {
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "adj_close": pl.Float64,
    "volume": pl.Float64,
}


class KrNaverPriceProvider:
    """``PriceProvider`` backed by the Naver Finance ``siseJson`` endpoint."""

    market: str = "KR"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.naver.com/",
            }
        )

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        """Return a polars DataFrame with daily OHLCV data sorted ascending.

        Columns
        -------
        date     : pl.Date
        open     : pl.Float64
        high     : pl.Float64
        low      : pl.Float64
        close    : pl.Float64
        adj_close: pl.Float64  (equals close — Naver has no separate adj col)
        volume   : pl.Float64
        """
        resp = self._client.get(
            _NAVER_URL,
            params={
                "symbol": ticker,
                "requestType": 1,
                "startTime": start.strftime("%Y%m%d"),
                "endTime": end.strftime("%Y%m%d"),
                "timeframe": "day",
            },
        )
        resp.raise_for_status()

        # Body is a Python literal (single quotes), not JSON.
        rows = ast.literal_eval(resp.text.strip())
        data = rows[1:]  # row 0 is the header

        if not data:
            return pl.DataFrame(schema=_EMPTY_SCHEMA)

        # Each row: [date(YYYYMMDD str), open, high, low, close, volume, foreign_rate]
        raw = pl.DataFrame(
            data,
            schema=[
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "foreign_rate",
            ],
            orient="row",
        )

        df = (
            raw.with_columns(
                pl.col("date").cast(pl.Utf8).str.to_date("%Y%m%d"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
            )
            .with_columns(
                pl.col("close").alias("adj_close"),  # Naver has no separate adj
            )
            .select(_OUTPUT_COLUMNS)
            .sort("date")
        )

        return df


# Satisfy the Protocol at import-time.
_: PriceProvider = KrNaverPriceProvider.__new__(KrNaverPriceProvider)  # type: ignore[assignment]
