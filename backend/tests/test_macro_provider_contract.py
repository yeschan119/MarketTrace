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


# FRED's standard (output_type=1) shape: current values, one vintage (today).
FRED_CURRENT_OBS = {
    "observations": [
        {"realtime_start": "2026-06-16", "realtime_end": "2026-06-16", "date": "2024-01-02", "value": "4.10"},
        {"realtime_start": "2026-06-16", "realtime_end": "2026-06-16", "date": "2024-01-03", "value": "4.20"},
    ]
}
# The 400 FRED returns for a daily series with too many vintages for output_type=4.
_VINTAGE_OVERFLOW = json.dumps(
    {
        "error_code": 400,
        "error_message": (
            "Bad Request.  There are 5045 vintage dates in the specified "
            "real-time period: 1900-01-01 to 9999-12-31.  This exceeds the "
            "maximum number of vintage dates allowed for output_type=4."
        ),
    }
)


class TestVintageOverflowFallback:
    """Daily series exceeding the output_type=4 vintage cap fall back to current values."""

    def _make_provider(self, *, requests: list[str] | None = None) -> FredMacroProvider:
        def handler(request: httpx.Request) -> httpx.Response:
            if requests is not None:
                requests.append(str(request.url))
            if "output_type=4" in str(request.url):
                return httpx.Response(
                    400, text=_VINTAGE_OVERFLOW, headers={"Content-Type": "application/json"}
                )
            return httpx.Response(
                200,
                text=json.dumps(FRED_CURRENT_OBS),
                headers={"Content-Type": "application/json"},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        return FredMacroProvider(api_key="k", client=client)

    def test_falls_back_to_current_observations(self):
        points = self._make_provider().get_observations("DGS10", date(2024, 1, 1))
        assert [p.reference_date for p in points] == [date(2024, 1, 2), date(2024, 1, 3)]
        assert points[1].released_value == pytest.approx(4.20)
        assert points[1].previous_value == pytest.approx(4.10)

    def test_released_at_dated_to_reference_date(self):
        # The fallback has no vintage date, so each value is dated to its period.
        points = self._make_provider().get_observations("DGS10", date(2024, 1, 1))
        assert points[0].released_at == datetime(2024, 1, 2, tzinfo=UTC)

    def test_fallback_request_drops_output_type_and_realtime_window(self):
        requests: list[str] = []
        self._make_provider(requests=requests).get_observations("DGS10", date(2024, 1, 1))
        assert len(requests) == 2  # the failed type=4 attempt, then the fallback
        fallback = requests[1]
        assert "output_type=4" not in fallback
        assert "realtime_start" not in fallback

    def test_non_overflow_400_still_raises(self):
        # A 400 that is not a vintage overflow must not be silently swallowed.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                text=json.dumps({"error_code": 400, "error_message": "Bad series id."}),
                headers={"Content-Type": "application/json"},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = FredMacroProvider(api_key="k", client=client)
        with pytest.raises(httpx.HTTPStatusError):
            provider.get_observations("NOPE", date(2024, 1, 1))
