"""FRED / ALFRED macroeconomic data provider.

Fetches economic series from the St. Louis Fed's FRED API, requesting the
*initial release* of each observation (ALFRED ``output_type=4``) so the value
stored is the one that was actually known on its release date — not a later
revision. This preserves vintage information and avoids the look-ahead bias the
blueprint (§9) warns against. Network access is injectable via ``httpx.Client``
so tests can supply a mock transport.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx

from markettrace.providers.base import MacroPoint, MacroProvider

__all__ = ["FredMacroProvider"]

_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
# ALFRED output_type 4 = "Initial release only": one row per reference period,
# carrying the value as first published and its release (realtime_start) date.
_INITIAL_RELEASE = 4
# output_type=4 requires an explicit real-time window covering every vintage;
# the API's default (today..today) matches no vintages and returns HTTP 400.
_REALTIME_START = "1900-01-01"
_REALTIME_END = "9999-12-31"


class FredMacroProvider:
    """``MacroProvider`` backed by the FRED/ALFRED observations API."""

    source: str = "fred"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client()

    def get_observations(self, series_id: str, since: date) -> list[MacroPoint]:
        """Return initial-release observations for *series_id* on/after *since*.

        Each point carries ``released_value`` (value as first published),
        ``released_at`` (the release/vintage date), and ``previous_value`` (the
        prior period's released value). Observations FRED marks missing (value
        ``"."``) are skipped, and ``previous_value`` chains across the kept rows.
        """
        resp = self._client.get(
            _FRED_URL,
            params={
                "series_id": series_id,
                "api_key": self._api_key or "",
                "file_type": "json",
                "observation_start": since.strftime("%Y-%m-%d"),
                "output_type": _INITIAL_RELEASE,
                # output_type=4 needs an explicit real-time window spanning all
                # vintages; the API default (today..today) finds none and 400s.
                "realtime_start": _REALTIME_START,
                "realtime_end": _REALTIME_END,
            },
        )
        resp.raise_for_status()

        rows = resp.json().get("observations", [])
        points: list[MacroPoint] = []
        prev: float | None = None
        for row in rows:
            raw_value = row.get("value", ".")
            if raw_value in (".", "", None):
                continue  # FRED missing marker — skip, do not break the chain key
            try:
                value = float(raw_value)
                ref_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
                released_at = datetime.strptime(
                    row["realtime_start"], "%Y-%m-%d"
                ).replace(tzinfo=UTC)
            except (KeyError, ValueError):
                continue

            points.append(
                MacroPoint(
                    series_id=series_id,
                    reference_date=ref_date,
                    released_value=value,
                    released_at=released_at,
                    previous_value=prev,
                )
            )
            prev = value

        points.sort(key=lambda p: p.reference_date)
        return points


# Satisfy the Protocol at import-time.
_: MacroProvider = FredMacroProvider.__new__(FredMacroProvider)  # type: ignore[assignment]
