"""Tests for TiingoPriceProvider using an injectable mock transport.

No network access is made; httpx.MockTransport intercepts all requests and
returns fixture JSON modelled on Tiingo's daily-prices response.
"""

from __future__ import annotations

import json
from datetime import date

import httpx
import polars as pl
import pytest

from markettrace.providers.base import PriceProvider
from markettrace.providers.tiingo import TiingoPriceProvider

# A two-row slice shaped like Tiingo's /tiingo/daily/{t}/prices response.
# Intentionally out of order to prove the provider sorts ascending.
TIINGO_ROWS = [
    {
        "date": "2024-05-16T00:00:00.000Z",
        "open": 171.0,
        "high": 173.0,
        "low": 170.0,
        "close": 172.5,
        "volume": 2_000_000,
        "adjClose": 172.0,
        "adjHigh": 172.5,
        "adjLow": 169.5,
        "adjOpen": 170.5,
        "adjVolume": 2_000_000,
        "divCash": 0.0,
        "splitFactor": 1.0,
    },
    {
        "date": "2024-05-15T00:00:00.000Z",
        "open": 169.0,
        "high": 170.0,
        "low": 168.0,
        "close": 169.5,
        "volume": 1_000_000,
        "adjClose": 169.0,
        "adjHigh": 169.5,
        "adjLow": 167.5,
        "adjOpen": 168.5,
        "adjVolume": 1_000_000,
        "divCash": 0.0,
        "splitFactor": 1.0,
    },
]


def _make_provider(rows=None, *, capture: dict | None = None) -> TiingoPriceProvider:
    body = json.dumps(TIINGO_ROWS if rows is None else rows)

    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture["url"] = str(request.url)
            capture["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, text=body, headers={"Content-Type": "application/json"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return TiingoPriceProvider(api_key="test-key", client=client)


class TestProtocolConformance:
    def test_satisfies_price_provider_protocol(self):
        provider = _make_provider()
        assert isinstance(provider, PriceProvider)

    def test_market_is_us(self):
        assert TiingoPriceProvider.market == "US"


class TestGetOhlcv:
    def test_returns_polars_dataframe(self):
        df = _make_provider().get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
        assert isinstance(df, pl.DataFrame)

    def test_exact_columns(self):
        df = _make_provider().get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
        assert df.columns == ["date", "open", "high", "low", "close", "adj_close", "volume"]

    def test_date_column_is_date_type(self):
        df = _make_provider().get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
        assert df.schema["date"] == pl.Date
        assert df["date"].to_list() == [date(2024, 5, 15), date(2024, 5, 16)]

    def test_sorted_ascending(self):
        df = _make_provider().get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
        dates = df["date"].to_list()
        assert dates == sorted(dates)

    def test_adj_close_maps_from_adjClose_not_close(self):
        df = _make_provider().get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
        first = df.row(0, named=True)  # 2024-05-15
        assert first["adj_close"] == pytest.approx(169.0)  # adjClose
        assert first["close"] == pytest.approx(169.5)      # close (different)

    def test_ohlcv_values(self):
        df = _make_provider().get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
        row = df.row(1, named=True)  # 2024-05-16
        assert row["open"] == pytest.approx(171.0)
        assert row["high"] == pytest.approx(173.0)
        assert row["low"] == pytest.approx(170.0)
        assert row["close"] == pytest.approx(172.5)
        assert row["volume"] == pytest.approx(2_000_000)


class TestRequestShape:
    def test_sends_authorization_token_header(self):
        capture: dict = {}
        _make_provider(capture=capture).get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
        assert capture["auth"] == "Token test-key"

    def test_url_includes_ticker_and_date_range(self):
        capture: dict = {}
        _make_provider(capture=capture).get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
        url = capture["url"]
        assert "/tiingo/daily/aapl/prices" in url
        assert "startDate=2024-05-15" in url
        assert "endDate=2024-05-16" in url

    def test_raises_on_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="Not Found")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = TiingoPriceProvider(api_key="k", client=client)
        with pytest.raises(httpx.HTTPStatusError):
            provider.get_ohlcv("AAPL", date(2024, 5, 15), date(2024, 5, 16))
