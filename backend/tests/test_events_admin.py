"""Tests for PATCH /events/{id} — human review of extracted events (Phase 2).

Covers auth gating, original-value snapshotting, validation, and the impact
rebuild that keeps signed_abnormal_return consistent after a direction edit.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.api.auth import create_token
from markettrace.api.deps import get_db, get_price_provider_factory
from markettrace.api.main import create_app
from markettrace.db.models import (
    Base,
    Document,
    DocumentEntity,
    Event,
    EventImpact,
    Instrument,
    ModelRun,
    Outcome,
    Price,
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


# ---------------------------------------------------------------------------
# Instrument correction (re-link a mis-classified company)
# ---------------------------------------------------------------------------

_EVENT_DATE = date(2026, 1, 2)


def _flat_price_frame() -> pl.DataFrame:
    """Constant OHLCV data spanning the recompute window."""
    start = _EVENT_DATE - timedelta(days=10)
    dates = [start + timedelta(days=i) for i in range(160)]
    n = len(dates)
    return pl.DataFrame(
        {
            "date": dates,
            "open": [100.0] * n,
            "high": [100.0] * n,
            "low": [100.0] * n,
            "close": [100.0] * n,
            "adj_close": [100.0] * n,
            "volume": [1_000_000.0] * n,
        }
    )


class _FlatPriceProvider:
    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        return _flat_price_frame()


class _RaisingPriceProvider:
    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        raise RuntimeError("price provider unavailable")


def _override_price_provider(client: TestClient, provider) -> None:
    client.app.dependency_overrides[get_price_provider_factory] = lambda: (
        lambda market: provider
    )


@pytest.fixture
def other_instrument(session: Session) -> Instrument:
    instrument = Instrument(
        market="KR", ticker="000660", name="SK hynix", industry="Tech"
    )
    session.add(instrument)
    session.flush()
    return instrument


def test_instrument_correction_relinks_and_recomputes(
    client: TestClient,
    token: str,
    seeded: dict,
    other_instrument: Instrument,
    session: Session,
) -> None:
    eid = seeded["event_id"]
    old_iid = seeded["instrument_id"]
    _override_price_provider(client, _FlatPriceProvider())

    resp = client.patch(
        f"/events/{eid}",
        json={"primary_instrument_id": other_instrument.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["primary_instrument_id"] == other_instrument.id
    assert body["primary_ticker"] == "000660"
    assert body["instrument_name"] == "SK hynix"
    assert body["original_primary_instrument_id"] == old_iid
    assert body["entities"] == ["000660"]
    assert body["reviewed_at"] is not None

    session.expire_all()
    event = session.get(Event, eid)
    assert event is not None
    assert event.primary_instrument_id == other_instrument.id
    assert event.entities == ["000660"]

    outcomes = session.scalars(select(Outcome).where(Outcome.event_id == eid)).all()
    assert outcomes
    assert {o.horizon_days for o in outcomes} == {1, 5, 20, 60}
    assert all(o.instrument_id == other_instrument.id for o in outcomes)
    assert all(o.abnormal_return == pytest.approx(0.0) for o in outcomes)

    impacts = session.scalars(
        select(EventImpact).where(EventImpact.event_id == eid)
    ).all()
    assert impacts
    assert all(i.instrument_id == other_instrument.id for i in impacts)

    assert session.scalars(
        select(Price).where(Price.instrument_id == other_instrument.id)
    ).first() is not None
    assert session.scalar(
        select(DocumentEntity).where(
            DocumentEntity.document_id == event.document_id,
            DocumentEntity.instrument_id == other_instrument.id,
        )
    )
    assert session.scalar(
        select(ModelRun).where(ModelRun.kind == "recompute_event_outcomes")
    )


def test_instrument_correction_unknown_instrument_422(
    client: TestClient, token: str, seeded: dict
) -> None:
    _override_price_provider(client, _FlatPriceProvider())
    resp = client.patch(
        f"/events/{seeded['event_id']}",
        json={"primary_instrument_id": 999999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_instrument_correction_price_failure_rolls_back(
    client: TestClient,
    token: str,
    seeded: dict,
    other_instrument: Instrument,
    session: Session,
) -> None:
    eid = seeded["event_id"]
    old_iid = seeded["instrument_id"]
    session.commit()
    _override_price_provider(client, _RaisingPriceProvider())

    resp = client.patch(
        f"/events/{eid}",
        json={"primary_instrument_id": other_instrument.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 502

    session.expire_all()
    event = session.get(Event, eid)
    assert event is not None
    assert event.primary_instrument_id == old_iid
    assert event.reviewed_at is None
    assert event.original_primary_instrument_id is None
    outcomes = session.scalars(select(Outcome).where(Outcome.event_id == eid)).all()
    assert {o.instrument_id for o in outcomes} == {old_iid}
    assert {o.horizon_days for o in outcomes} == {1, 5}
