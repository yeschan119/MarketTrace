"""Tests for the MarketTrace read API."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.api.deps import get_db
from markettrace.api.main import create_app
from markettrace.db.models import (
    Base,
    Document,
    Event,
    EventImpact,
    Instrument,
    MacroObservation,
    Outcome,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


@pytest.fixture(scope="module")
def thread_safe_engine():
    """In-memory SQLite engine safe for cross-thread use (TestClient runs in a worker thread)."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def ts_session(thread_safe_engine) -> Iterator[Session]:
    """Session from the thread-safe engine, rolled back after each test."""
    factory = sessionmaker(bind=thread_safe_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(ts_session: Session) -> Iterator[TestClient]:
    """TestClient with get_db overridden to use the thread-safe test session."""
    application = create_app()

    def override_get_db() -> Iterator[Session]:
        yield ts_session

    application.dependency_overrides[get_db] = override_get_db
    with TestClient(application) as c:
        yield c


@pytest.fixture
def seeded(ts_session: Session) -> dict:
    """Seed one Instrument, Document, Event, and 3 Outcomes. Return their ids."""
    instrument = Instrument(
        market="US",
        ticker="AAPL",
        name="Apple Inc.",
    )
    ts_session.add(instrument)
    ts_session.flush()

    document = Document(
        source="reuters",
        external_id="doc-001",
        url="https://example.com/article/1",
        title="Apple Reports Record Earnings",
        content_hash="abc123def456",
        market="US",
        published_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        first_seen_at=_now(),
    )
    ts_session.add(document)
    ts_session.flush()

    event = Event(
        document_id=document.id,
        primary_instrument_id=instrument.id,
        event_type="earnings",
        direction="positive",
        confidence=0.92,
        horizon_days=5,
        model="gpt-4",
        model_version="2024-01",
        analyzed_at=_now(),
        entities=["AAPL"],
        industries=["Technology"],
        channels=["news"],
        evidence=["Record Q4 revenue of $119B"],
    )
    ts_session.add(event)
    ts_session.flush()

    for days, raw, mkt, abnormal in [
        (1, 0.02, 0.005, 0.015),
        (5, 0.05, 0.01, 0.04),
        (20, 0.08, 0.02, 0.06),
    ]:
        ts_session.add(
            Outcome(
                event_id=event.id,
                instrument_id=instrument.id,
                horizon_days=days,
                raw_return=raw,
                market_return=mkt,
                abnormal_return=abnormal,
                computed_at=_now(),
            )
        )
    ts_session.flush()

    return {"instrument_id": instrument.id, "event_id": event.id, "document": document}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /events
# ---------------------------------------------------------------------------


def test_list_events_returns_one_item(client: TestClient, seeded: dict) -> None:
    resp = client.get("/events")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["primary_ticker"] == "AAPL"
    assert item["instrument_name"] == "Apple Inc."
    assert "published_at" in item


# ---------------------------------------------------------------------------
# GET /events/{id}
# ---------------------------------------------------------------------------


def test_get_event_detail(client: TestClient, seeded: dict) -> None:
    event_id = seeded["event_id"]
    resp = client.get(f"/events/{event_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == event_id
    assert data["document"]["title"] == "Apple Reports Record Earnings"
    assert data["entities"] == ["AAPL"]
    # 3 outcomes sorted by horizon_days ascending
    horizons = [o["horizon_days"] for o in data["outcomes"]]
    assert horizons == [1, 5, 20]


def test_get_event_detail_404(client: TestClient) -> None:
    resp = client.get("/events/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /instruments/{id}/timeline
# ---------------------------------------------------------------------------


def test_instrument_timeline(client: TestClient, seeded: dict) -> None:
    instrument_id = seeded["instrument_id"]
    event_id = seeded["event_id"]
    resp = client.get(f"/instruments/{instrument_id}/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"]["ticker"] == "AAPL"
    assert len(data["events"]) == 1
    assert data["events"][0]["id"] == event_id


def test_instrument_timeline_404(client: TestClient) -> None:
    resp = client.get("/instruments/99999/timeline")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /stats/event-types
# ---------------------------------------------------------------------------


def test_event_type_stats_empty(client: TestClient) -> None:
    resp = client.get("/stats/event-types")
    assert resp.status_code == 200
    assert resp.json() == []


def test_event_type_stats_aggregates(client: TestClient, seeded: dict, ts_session: Session) -> None:
    instrument_id = seeded["instrument_id"]
    # Two impacts in the same (event_type, horizon) bucket but distinct events
    # (the table is unique on event_id + horizon_days).
    for ev_id, ar in ((seeded["event_id"], 0.02), (seeded["event_id"] + 1000, 0.04)):
        ts_session.add(
            EventImpact(
                event_id=ev_id,
                instrument_id=instrument_id,
                event_type="earnings",
                industry="Technology",
                direction="positive",
                horizon_days=1,
                abnormal_return=ar,
                signed_abnormal_return=ar,
                computed_at=_now(),
            )
        )
    ts_session.flush()

    resp = client.get("/stats/event-types")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    row = data[0]
    assert row["event_type"] == "earnings"
    assert row["horizon_days"] == 1
    assert row["count"] == 2
    assert row["mean_abnormal_return"] == pytest.approx(0.03)


def _macro_row(series_id: str, ref: datetime, value: float, surprise: float | None):
    return MacroObservation(
        series_id=series_id,
        reference_date=ref.date(),
        released_value=value,
        previous_value=None,
        expected_value=value - 1.0,
        expected_source="baseline",
        surprise_score=surprise,
        occurred_at=ref,
        published_at=ref,
        first_seen_at=_now(),
        revision=0,
        source="fred",
    )


def test_macro_observations_returns_latest_per_series(client, ts_session):
    # Two CPI releases (latest = March) + one UNRATE release.
    ts_session.add(_macro_row("CPIAUCSL", datetime(2024, 1, 1, tzinfo=UTC), 300.0, 1.5))
    ts_session.add(_macro_row("CPIAUCSL", datetime(2024, 3, 1, tzinfo=UTC), 303.0, 2.0))
    ts_session.add(_macro_row("UNRATE", datetime(2024, 3, 1, tzinfo=UTC), 3.9, -0.5))
    ts_session.flush()

    resp = client.get("/macro/observations")
    assert resp.status_code == 200
    data = resp.json()
    # One row per series, sorted by series id.
    assert [r["series_id"] for r in data] == ["CPIAUCSL", "UNRATE"]
    cpi = data[0]
    assert cpi["reference_date"] == "2024-03-01"  # latest reference period
    assert cpi["released_value"] == pytest.approx(303.0)
    assert cpi["surprise_score"] == pytest.approx(2.0)
    assert cpi["expected_source"] == "baseline"


def test_macro_observations_series_filter(client, ts_session):
    ts_session.add(_macro_row("CPIAUCSL", datetime(2024, 3, 1, tzinfo=UTC), 303.0, 2.0))
    ts_session.add(_macro_row("UNRATE", datetime(2024, 3, 1, tzinfo=UTC), 3.9, -0.5))
    ts_session.flush()

    resp = client.get("/macro/observations", params={"series": "UNRATE"})
    assert resp.status_code == 200
    data = resp.json()
    assert [r["series_id"] for r in data] == ["UNRATE"]


def test_event_type_contributions_expose_per_event_returns(
    client: TestClient, seeded: dict, ts_session: Session
) -> None:
    # Two earnings EventImpacts at D+5 with distinct abnormal returns; the
    # /stats/event-types mean over them must be reconstructable from the
    # per-event contributions the endpoint returns.
    event_id = seeded["event_id"]
    instrument_id = seeded["instrument_id"]
    ts_session.add(
        EventImpact(
            event_id=event_id,
            instrument_id=instrument_id,
            event_type="earnings",
            direction="positive",
            horizon_days=5,
            abnormal_return=0.04,
            computed_at=_now(),
        )
    )
    ts_session.flush()

    resp = client.get("/stats/event-types/contributions")
    assert resp.status_code == 200
    data = resp.json()
    earnings_d5 = [
        c for c in data if c["event_type"] == "earnings" and c["horizon_days"] == 5
    ]
    assert len(earnings_d5) == 1
    row = earnings_d5[0]
    assert row["event_id"] == int(event_id)
    assert row["abnormal_return"] == pytest.approx(0.04)
    assert row["primary_ticker"] == "AAPL"
    assert row["market"] == "US"
    assert row["direction"] == "positive"


def test_backtest_route_exposes_cost_and_coverage_fields(client: TestClient) -> None:
    resp = client.get("/stats/backtest")
    assert resp.status_code == 200
    data = resp.json()
    # One result per standard horizon.
    assert [r["horizon_days"] for r in data] == [1, 5, 20, 60]
    for row in data:
        # Default model is the history model.
        assert row["model"] == "event_type_history"
        # Cost + net-of-cost fields (Phase 4 "거래 현실 반영") are surfaced.
        assert "mean_strategy_return_net" in row
        assert row["commission_per_trade"] >= 0.0
        assert row["slippage_per_trade"] >= 0.0
        # Coverage honesty: totals reconcile with dropped/usable split.
        assert row["n_events_total"] == row["n_events"] + row["n_dropped_no_outcome"]


def test_backtest_route_selects_direction_model(client: TestClient) -> None:
    resp = client.get("/stats/backtest", params={"model": "llm_direction"})
    assert resp.status_code == 200
    data = resp.json()
    assert [r["horizon_days"] for r in data] == [1, 5, 20, 60]
    assert all(r["model"] == "llm_direction" for r in data)


def test_backtest_route_rejects_unknown_model(client: TestClient) -> None:
    resp = client.get("/stats/backtest", params={"model": "bogus"})
    assert resp.status_code == 400


def test_macro_decomposition_route(client, ts_session):
    ts_session.add(_macro_row("CPIAUCSL", datetime(2024, 3, 1, tzinfo=UTC), 303.0, 2.0))
    ts_session.add(_macro_row("UNRATE", datetime(2024, 3, 1, tzinfo=UTC), 3.9, -0.5))
    ts_session.flush()

    resp = client.get("/stats/macro-decomposition")
    assert resp.status_code == 200
    data = resp.json()
    # One backtest per (series, standard horizon).
    assert {r["series_id"] for r in data} == {"CPIAUCSL", "UNRATE"}
    cpi_horizons = sorted(r["horizon_days"] for r in data if r["series_id"] == "CPIAUCSL")
    assert cpi_horizons == [1, 5, 20, 60]
    for row in data:
        assert "information_coefficient" in row
        assert "mean_strategy_return_net" in row
