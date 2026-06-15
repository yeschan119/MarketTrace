"""Tests for FredMacroProvider using an injectable mock transport (no network)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import httpx
import pytest

from markettrace.providers.base import MacroPoint, MacroProvider
from markettrace.providers.fred import FredMacroProvider

# FRED /series/observations shape (output_type=4, initial release only).
# Includes a "." missing marker that must be skipped, and is in ascending order.
FRED_OBS = {
    "observations": [
        {"realtime_start": "2024-02-13", "realtime_end": "9999-12-31", "date": "2024-01-01", "value": "300.0"},
        {"realtime_start": "2024-03-12", "realtime_end": "9999-12-31", "date": "2024-02-01", "value": "."},
        {"realtime_start": "2024-04-10", "realtime_end": "9999-12-31", "date": "2024-03-01", "value": "303.0"},
    ]
}


def _make_provider(*, capture: dict | None = None) -> FredMacroProvider:
    body = json.dumps(FRED_OBS)

    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture["url"] = str(request.url)
        return httpx.Response(200, text=body, headers={"Content-Type": "application/json"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FredMacroProvider(api_key="test-key", client=client)


class TestProtocolConformance:
    def test_satisfies_macro_provider_protocol(self):
        assert isinstance(_make_provider(), MacroProvider)

    def test_source_is_fred(self):
        assert FredMacroProvider.source == "fred"


class TestGetObservations:
    def test_returns_macro_points(self):
        points = _make_provider().get_observations("CPIAUCSL", date(2020, 1, 1))
        assert all(isinstance(p, MacroPoint) for p in points)

    def test_skips_missing_value_marker(self):
        points = _make_provider().get_observations("CPIAUCSL", date(2020, 1, 1))
        # The "." row (2024-02-01) is dropped -> 2 valid points.
        assert [p.reference_date for p in points] == [date(2024, 1, 1), date(2024, 3, 1)]

    def test_parses_released_value_and_release_date(self):
        points = _make_provider().get_observations("CPIAUCSL", date(2020, 1, 1))
        first = points[0]
        assert first.released_value == pytest.approx(300.0)
        assert first.released_at == datetime(2024, 2, 13, tzinfo=UTC)

    def test_previous_value_chains_over_kept_points(self):
        points = _make_provider().get_observations("CPIAUCSL", date(2020, 1, 1))
        assert points[0].previous_value is None
        assert points[1].previous_value == pytest.approx(300.0)

    def test_sorted_ascending(self):
        points = _make_provider().get_observations("CPIAUCSL", date(2020, 1, 1))
        dates = [p.reference_date for p in points]
        assert dates == sorted(dates)


class TestRequestShape:
    def test_request_uses_initial_release_output_type(self):
        capture: dict = {}
        _make_provider(capture=capture).get_observations("CPIAUCSL", date(2020, 1, 1))
        url = capture["url"]
        assert "series_id=CPIAUCSL" in url
        assert "output_type=4" in url
        assert "observation_start=2020-01-01" in url
        # output_type=4 needs an explicit real-time window or FRED returns 400.
        assert "realtime_start=1900-01-01" in url
        assert "realtime_end=9999-12-31" in url

    def test_raises_on_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="Bad Request")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = FredMacroProvider(api_key="k", client=client)
        with pytest.raises(httpx.HTTPStatusError):
            provider.get_observations("CPIAUCSL", date(2020, 1, 1))
