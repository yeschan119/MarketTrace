"""Tests for KrNaverPriceProvider using an injectable mock transport.

No network access is made; httpx.MockTransport intercepts all requests and
returns fixture data modelled on Naver Finance's siseJson response format.
"""

from __future__ import annotations

from datetime import date

import httpx
import polars as pl
import pytest

from markettrace.providers.base import PriceProvider
from markettrace.providers.kr_naver import KrNaverPriceProvider

# Two-row slice shaped like Naver's siseJson Python-literal response.
# Rows are intentionally out of order to prove the provider sorts ascending.
NAVER_BODY = (
    "[['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율'],\n"
    '["20260402", 192600, 193600, 175000, 178400, 38615231, 48.4],\n'
    '["20260401", 179000, 190800, 178000, 189600, 32390251, 48.43]]'
)

# Header-only body → empty DataFrame (no crash expected).
NAVER_BODY_EMPTY = "[['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율']]"


def _make_provider(body: str = NAVER_BODY, *, capture: dict | None = None) -> KrNaverPriceProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture["url"] = str(request.url)
        return httpx.Response(200, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return KrNaverPriceProvider(client=client)


class TestProtocolConformance:
    def test_satisfies_price_provider_protocol(self):
        provider = _make_provider()
        assert isinstance(provider, PriceProvider)

    def test_market_is_kr(self):
        assert KrNaverPriceProvider.market == "KR"


class TestGetOhlcv:
    def test_returns_polars_dataframe(self):
        df = _make_provider().get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        assert isinstance(df, pl.DataFrame)

    def test_exact_columns(self):
        df = _make_provider().get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        assert df.columns == ["date", "open", "high", "low", "close", "adj_close", "volume"]

    def test_date_column_is_date_type(self):
        df = _make_provider().get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        assert df.schema["date"] == pl.Date
        assert df["date"].to_list() == [date(2026, 4, 1), date(2026, 4, 2)]

    def test_sorted_ascending(self):
        df = _make_provider().get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        dates = df["date"].to_list()
        assert dates == sorted(dates)

    def test_adj_close_equals_close(self):
        df = _make_provider().get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        assert df["adj_close"].to_list() == df["close"].to_list()

    def test_ohlcv_values(self):
        df = _make_provider().get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        row = df.row(1, named=True)  # 2026-04-02
        assert row["open"] == pytest.approx(192600.0)
        assert row["high"] == pytest.approx(193600.0)
        assert row["low"] == pytest.approx(175000.0)
        assert row["close"] == pytest.approx(178400.0)
        assert row["volume"] == pytest.approx(38615231.0)

    def test_empty_body_returns_empty_dataframe(self):
        df = _make_provider(NAVER_BODY_EMPTY).get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        assert isinstance(df, pl.DataFrame)
        assert df.columns == ["date", "open", "high", "low", "close", "adj_close", "volume"]
        assert len(df) == 0


class TestRequestShape:
    def test_url_includes_symbol(self):
        capture: dict = {}
        _make_provider(capture=capture).get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        assert "symbol=005930" in capture["url"]

    def test_url_includes_timeframe_day(self):
        capture: dict = {}
        _make_provider(capture=capture).get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        assert "timeframe=day" in capture["url"]

    def test_url_includes_start_and_end_time(self):
        capture: dict = {}
        _make_provider(capture=capture).get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
        url = capture["url"]
        assert "startTime=20260401" in url
        assert "endTime=20260402" in url

    def test_raises_on_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="Not Found")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = KrNaverPriceProvider(client=client)
        with pytest.raises(httpx.HTTPStatusError):
            provider.get_ohlcv("005930", date(2026, 4, 1), date(2026, 4, 2))
