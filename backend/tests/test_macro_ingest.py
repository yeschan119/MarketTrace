"""Integration test for the macro ingestion pipeline on in-memory SQLite."""

from __future__ import annotations

from datetime import UTC, date, datetime

from markettrace.db.models import MacroObservation, ModelRun
from markettrace.impact.macro_surprise import build_macro_observations
from markettrace.pipeline.macro_ingest import ingest_macro_series
from markettrace.providers.base import MacroPoint

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


class _StubMacroProvider:
    """Returns fixed initial-release points for any series (no network)."""

    source = "fred"

    def __init__(self, points_by_series: dict[str, list[MacroPoint]]):
        self._points = points_by_series

    def get_observations(self, series_id: str, since: date) -> list[MacroPoint]:
        return list(self._points.get(series_id, []))


def _series_points(series_id: str) -> list[MacroPoint]:
    values = [100.0, 102.0, 101.0, 104.0, 108.0]
    dates = [date(2024, m, 1) for m in range(1, 6)]
    prev = None
    pts = []
    for d, v in zip(dates, values, strict=True):
        pts.append(
            MacroPoint(
                series_id=series_id,
                reference_date=d,
                released_value=v,
                released_at=datetime(d.year, d.month, d.day, tzinfo=UTC),
                previous_value=prev,
            )
        )
        prev = v
    return pts


def test_ingest_persists_observations_with_surprise(db_session):
    provider = _StubMacroProvider({"CPIAUCSL": _series_points("CPIAUCSL")})

    inserted = ingest_macro_series(
        db_session, provider, ["CPIAUCSL"], now=_NOW, since=date(2020, 1, 1)
    )

    assert inserted == {"CPIAUCSL": 5}
    rows = db_session.query(MacroObservation).order_by(MacroObservation.reference_date).all()
    assert len(rows) == 5
    assert all(r.series_id == "CPIAUCSL" and r.source == "fred" for r in rows)
    # Later points carry a computed surprise once enough history exists.
    assert rows[3].surprise_score is not None
    assert rows[3].expected_source == "baseline"
    # Provenance recorded once.
    runs = db_session.query(ModelRun).filter(ModelRun.kind == "macro_ingest").all()
    assert len(runs) == 1
    assert runs[0].params["inserted"] == {"CPIAUCSL": 5}


def test_ingest_is_idempotent(db_session):
    provider = _StubMacroProvider({"CPIAUCSL": _series_points("CPIAUCSL")})

    first = ingest_macro_series(db_session, provider, ["CPIAUCSL"], now=_NOW)
    second = ingest_macro_series(db_session, provider, ["CPIAUCSL"], now=_NOW)

    assert first == {"CPIAUCSL": 5}
    assert second == {"CPIAUCSL": 0}  # nothing new on re-run
    assert db_session.query(MacroObservation).count() == 5
    # Only the first run (which inserted rows) records a ModelRun.
    assert db_session.query(ModelRun).filter(ModelRun.kind == "macro_ingest").count() == 1


class _RecordingProvider:
    """Records the *since* it was asked for and only returns points on/after it."""

    source = "fred"

    def __init__(self, points_by_series: dict[str, list[MacroPoint]]):
        self._points = points_by_series
        self.calls: list[tuple[str, date]] = []

    def get_observations(self, series_id: str, since: date) -> list[MacroPoint]:
        self.calls.append((series_id, since))
        return [p for p in self._points.get(series_id, []) if p.reference_date >= since]


def test_repeat_fetch_is_incremental_from_last_reference_date(db_session):
    """A series already in the DB is re-fetched from its latest stored date, not *since*."""
    points = _series_points("CPIAUCSL")
    provider = _RecordingProvider({"CPIAUCSL": points})

    ingest_macro_series(
        db_session, provider, ["CPIAUCSL"], now=_NOW, since=date(2020, 1, 1)
    )
    ingest_macro_series(
        db_session, provider, ["CPIAUCSL"], now=_NOW, since=date(2020, 1, 1)
    )

    first_since = provider.calls[0][1]
    second_since = provider.calls[1][1]
    assert first_since == date(2020, 1, 1)  # empty series -> the floor
    assert second_since == date(2024, 5, 1)  # latest stored reference_date


def test_incremental_new_release_surprise_matches_full_history(db_session):
    """A point appended on a later run gets the SAME surprise a full rebuild would give."""
    base = _series_points("CPIAUCSL")
    provider = _RecordingProvider({"CPIAUCSL": base})

    ingest_macro_series(db_session, provider, ["CPIAUCSL"], since=date(2020, 1, 1), now=_NOW)

    # A new release lands; only the newest point is fetched on the second run.
    new_point = MacroPoint(
        series_id="CPIAUCSL",
        reference_date=date(2024, 6, 1),
        released_value=99.0,  # a sharp move so the surprise is clearly non-zero
        released_at=datetime(2024, 6, 1, tzinfo=UTC),
        previous_value=108.0,
    )
    provider._points["CPIAUCSL"] = base + [new_point]

    inserted = ingest_macro_series(
        db_session, provider, ["CPIAUCSL"], since=date(2020, 1, 1), now=_NOW
    )
    assert inserted == {"CPIAUCSL": 1}  # only the new release

    row = (
        db_session.query(MacroObservation)
        .filter(MacroObservation.reference_date == date(2024, 6, 1))
        .one()
    )
    # The surprise computed incrementally (history seeded from the DB) equals the
    # surprise from rebuilding the whole series in one shot — no history lost.
    full = build_macro_observations(base + [new_point], now=_NOW)
    expected_surprise = full[-1].surprise_score
    assert expected_surprise is not None
    assert row.surprise_score == expected_surprise


class _PartlyFailingProvider:
    """Returns points for healthy series; raises for a named bad series."""

    source = "fred"

    def __init__(self, points_by_series: dict[str, list[MacroPoint]], bad: str):
        self._points = points_by_series
        self._bad = bad

    def get_observations(self, series_id: str, since: date) -> list[MacroPoint]:
        if series_id == self._bad:
            raise RuntimeError("boom: simulated FRED failure")
        return list(self._points.get(series_id, []))


def test_one_failing_series_does_not_abort_the_rest(db_session):
    """A series that errors is logged + skipped; healthy series still persist."""
    provider = _PartlyFailingProvider(
        {"CPIAUCSL": _series_points("CPIAUCSL")}, bad="DGS10"
    )

    inserted = ingest_macro_series(
        db_session, provider, ["CPIAUCSL", "DGS10"], now=_NOW, since=date(2020, 1, 1)
    )

    assert inserted == {"CPIAUCSL": 5, "DGS10": 0}
    rows = db_session.query(MacroObservation).all()
    assert len(rows) == 5
    assert {r.series_id for r in rows} == {"CPIAUCSL"}
    # The healthy series' rows were committed despite the other series failing.
    assert db_session.query(ModelRun).filter(ModelRun.kind == "macro_ingest").count() == 1
