"""Tiingo daily OHLCV price provider.

Downloads end-of-day price data from the Tiingo REST API for US-listed
tickers.  Network access is injectable via ``httpx.Client`` so tests can supply
a mock transport.

Unlike Stooq, Tiingo publishes a genuine split/dividend-adjusted close
(``adjClose``), which is mapped to the ``adj_close`` column.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date

import httpx
import polars as pl

from markettrace.providers.base import PriceProvider

__all__ = ["TiingoPriceProvider"]

_TIINGO_URL = "https://api.tiingo.com/tiingo/daily/{ticker}/prices"
# Tiingo throttles bursty clients (notably its free tier: ~50 req/hour) with 429.
# Like the SEC provider, space requests and retry 429/503 with bounded backoff.
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_BACKOFF_BASE = 1.0
# Cap any single wait so a free-tier hourly-quota ``Retry-After`` (which can be
# ~3600s) doesn't hang the run for an hour: the filing fails gracefully and an
# idempotent re-run resumes once the quota window resets.
_DEFAULT_MAX_RETRY_DELAY = 20.0
_RETRY_STATUS = frozenset({429, 503})


class TiingoPriceProvider:
    """``PriceProvider`` backed by the Tiingo daily-prices REST API."""

    market: str = "US"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        *,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        max_retry_delay: float = _DEFAULT_MAX_RETRY_DELAY,
        min_request_interval: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client()
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._max_retry_delay = max_retry_delay
        self._min_interval = min_request_interval
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def _get(self, url: str, *, params: dict, headers: dict) -> httpx.Response:
        """GET *url*, spacing requests and retrying Tiingo throttle responses.

        Mirrors the SEC provider: waits ``min_request_interval`` since the prior
        request, then retries 429/503 up to ``max_retries`` times with bounded
        backoff (honoring a capped ``Retry-After``). The last response is returned
        even when still throttled, so the caller's ``raise_for_status`` surfaces a
        genuine, persistent failure.
        """
        resp: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            self._throttle()
            resp = self._client.get(url, params=params, headers=headers)
            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                self._sleep(self._retry_delay(resp, attempt))
                continue
            break
        assert resp is not None  # loop runs at least once
        return resp

    def _throttle(self) -> None:
        """Sleep so consecutive requests are at least ``min_request_interval`` apart."""
        if self._min_interval <= 0:
            return
        if self._last_request_at is not None:
            wait = self._min_interval - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        """Seconds to wait before a retry: capped ``Retry-After`` if given, else backoff."""
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), self._max_retry_delay)
            except ValueError:
                pass  # HTTP-date form — fall back to backoff
        return min(self._backoff_base * (2**attempt), self._max_retry_delay)

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

        resp = self._get(
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
