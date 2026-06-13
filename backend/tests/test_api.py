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
from markettrace.db.models import Base, Document, Event, Instrument, Outcome


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
