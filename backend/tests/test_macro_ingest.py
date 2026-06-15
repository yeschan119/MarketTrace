"""Integration test for the macro ingestion pipeline on in-memory SQLite."""

from __future__ import annotations

from datetime import UTC, date, datetime

from markettrace.db.models import MacroObservation, ModelRun
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
