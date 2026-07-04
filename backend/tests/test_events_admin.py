"""Tests for PATCH /events/{id} — human review of extracted events (Phase 2).

Covers auth gating, original-value snapshotting, validation, and the impact
rebuild that keeps signed_abnormal_return consistent after a direction edit.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.api.auth import create_token
from markettrace.api.deps import get_db
from markettrace.api.main import create_app
from markettrace.db.models import (
    Base,
    Document,
    Event,
    EventImpact,
    Instrument,
    Outcome,
)
from markettrace.impact.event_impacts import build_event_impacts
from markettrace.impact.returns import OutcomeResult


class _AuthSettings:
    admin_username = "admin"
    admin_password = "pw"
    auth_secret = "secret-xyz-123"

    @property
    def cors_origins_list(self) -> list[str]:
        return ["http://localhost:3000"]


def _now() -> datetime:
    return datetime.now(tz=UTC)


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    s = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(session, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: _AuthSettings())
    app = create_app()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def token(monkeypatch) -> str:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: _AuthSettings())
    return create_token()


@pytest.fixture
def seeded(session: Session) -> dict:
    """One positive 'earnings' event with 2 outcomes and matching impacts."""
    instrument = Instrument(market="KR", ticker="005930", name="Samsung", industry="Tech")
    session.add(instrument)
    session.flush()

    document = Document(
        source="opendart",
        external_id="doc-1",
        url="https://example.com/1",
        title="Filing",
        content_hash="hash1",
        market="KR",
        published_at=datetime(2026, 1, 2, tzinfo=UTC),
        first_seen_at=_now(),
    )
    session.add(document)
    session.flush()

    event = Event(
        document_id=document.id,
        primary_instrument_id=instrument.id,
        event_type="earnings_release",
        direction="positive",
        confidence=0.9,
        horizon_days=5,
        model="gpt-x",
        model_version="v1",
        analyzed_at=_now(),
        entities=["005930"],
        industries=["Tech"],
        channels=["opendart"],
        evidence=["e"],
    )
    session.add(event)
    session.flush()

    outcomes = [(1, 0.02), (5, -0.04)]  # abnormal returns of opposite sign
    results = []
    for days, ar in outcomes:
        session.add(
            Outcome(
                event_id=event.id,
                instrument_id=instrument.id,
                horizon_days=days,
                raw_return=ar,
                market_return=0.0,
                abnormal_return=ar,
                computed_at=_now(),
            )
        )
        results.append(
            OutcomeResult(horizon_days=days, raw_return=ar, market_return=0.0, abnormal_return=ar)
        )
    for impact in build_event_impacts(event, results, industry="Tech", computed_at=_now()):
        session.add(impact)
    session.flush()

    return {"event_id": event.id, "instrument_id": instrument.id}


def _impacts(session: Session, event_id: int) -> dict[int, float | None]:
    rows = session.scalars(
        select(EventImpact).where(EventImpact.event_id == event_id)
    ).all()
    return {r.horizon_days: r.signed_abnormal_return for r in rows}


def test_review_requires_auth(client: TestClient, seeded: dict) -> None:
    resp = client.patch(f"/events/{seeded['event_id']}", json={"direction": "negative"})
    assert resp.status_code == 401


def test_review_404_for_missing_event(client: TestClient, token: str) -> None:
    resp = client.patch(
        "/events/999999",
        json={"direction": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_review_rejects_invalid_direction(
    client: TestClient, token: str, seeded: dict
) -> None:
    resp = client.patch(
        f"/events/{seeded['event_id']}",
        json={"direction": "sideways"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_direction_edit_snapshots_original_and_rebuilds_impacts(
    client: TestClient, token: str, seeded: dict, session: Session
) -> None:
    eid = seeded["event_id"]
    # Before: positive direction → signed = +abnormal.
    assert _impacts(session, eid) == {1: 0.02, 5: -0.04}

    resp = client.patch(
        f"/events/{eid}",
        json={"direction": "negative"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "negative"
    assert body["original_direction"] == "positive"
    assert body["reviewed_at"] is not None

    # After: negative direction → signed flips sign on every horizon.
    session.expire_all()
    assert _impacts(session, eid) == {1: -0.02, 5: 0.04}


def test_confidence_only_edit_snapshots_but_keeps_direction(
    client: TestClient, token: str, seeded: dict, session: Session
) -> None:
    eid = seeded["event_id"]
    before = _impacts(session, eid)

    resp = client.patch(
        f"/events/{eid}",
        json={"confidence": 0.5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["confidence"] == 0.5
    assert body["direction"] == "positive"
    assert body["original_confidence"] == 0.9

    session.expire_all()
    assert _impacts(session, eid) == before  # direction unchanged → impacts intact
