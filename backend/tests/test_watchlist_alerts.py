"""Tests for the watchlist + in-app alerts feature (Phase 5).

Covers the pure alert-assessment logic, alert generation over watched
instruments (with significance stubbed for determinism), and the watchlist /
alerts API (auth gating, unread ordering, mark-read).
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
    Alert,
    Base,
    Document,
    Event,
    Instrument,
    WatchlistItem,
)
from markettrace.impact import alerting
from markettrace.impact.alerting import assess_event_alert, generate_watchlist_alerts
from markettrace.impact.significance import EventTypeSignificance


class _AuthSettings:
    admin_username = "admin"
    admin_password = "pw"
    auth_secret = "secret-xyz-123"

    @property
    def cors_origins_list(self) -> list[str]:
        return ["http://localhost:3000"]


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _sig(event_type, horizon, mean, *, significant=True, sufficient=True, p=0.001):
    return EventTypeSignificance(
        event_type=event_type,
        horizon_days=horizon,
        count=20,
        mean_abnormal_return=mean,
        std_abnormal_return=0.05,
        t_stat=-5.0 if (mean or 0) < 0 else 5.0,
        p_value=p,
        significant_5pct=significant,
        sufficient_sample=sufficient,
    )


# ---------------------------------------------------------------------------
# assess_event_alert (pure)
# ---------------------------------------------------------------------------

class TestAssessEventAlert:
    def test_conflict_when_direction_opposes_drift(self):
        # Model says positive; validated drift is negative (insider −6.6%).
        kind = assess_event_alert(
            direction="positive",
            event_type="insider_trading",
            horizon_days=5,
            significance=[_sig("insider_trading", 5, -0.066)],
        )
        assert kind == "conflict"

    def test_significant_when_direction_agrees(self):
        kind = assess_event_alert(
            direction="negative",
            event_type="insider_trading",
            horizon_days=5,
            significance=[_sig("insider_trading", 5, -0.066)],
        )
        assert kind == "significant"

    def test_significant_when_model_neutral(self):
        kind = assess_event_alert(
            direction="neutral",
            event_type="insider_trading",
            horizon_days=5,
            significance=[_sig("insider_trading", 5, -0.066)],
        )
        assert kind == "significant"

    def test_none_when_type_not_significant(self):
        kind = assess_event_alert(
            direction="positive",
            event_type="earnings",
            horizon_days=5,
            significance=[_sig("earnings", 5, -0.02, significant=False)],
        )
        assert kind is None

    def test_none_when_no_matching_type(self):
        kind = assess_event_alert(
            direction="positive",
            event_type="product",
            horizon_days=5,
            significance=[_sig("insider_trading", 5, -0.066)],
        )
        assert kind is None

    def test_falls_back_to_lowest_p_when_horizon_absent(self):
        kind = assess_event_alert(
            direction="positive",
            event_type="insider_trading",
            horizon_days=99,  # no row at this horizon
            significance=[
                _sig("insider_trading", 5, -0.066, p=0.001),
                _sig("insider_trading", 20, 0.01, p=0.2, significant=False),
            ],
        )
        # Only the significant (5d, negative) row qualifies → conflict.
        assert kind == "conflict"


# ---------------------------------------------------------------------------
# generate_watchlist_alerts
# ---------------------------------------------------------------------------

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


_SEED_COUNTER = [0]


def _seed_event(session, *, ticker=None, event_type="insider_trading", direction="positive"):
    _SEED_COUNTER[0] += 1
    n = _SEED_COUNTER[0]
    ticker = ticker or f"00593{n}"
    inst = Instrument(market="KR", ticker=ticker, name="Samsung", industry="Tech")
    session.add(inst)
    session.flush()
    doc = Document(
        source="opendart",
        external_id=f"doc-{ticker}-{n}",
        url="https://example.com/1",
        title="Filing",
        content_hash=f"hash-{ticker}-{n}",
        market="KR",
        published_at=datetime(2026, 1, 2, tzinfo=UTC),
        first_seen_at=_now(),
    )
    session.add(doc)
    session.flush()
    ev = Event(
        document_id=doc.id,
        primary_instrument_id=inst.id,
        event_type=event_type,
        direction=direction,
        confidence=0.9,
        horizon_days=5,
        model="m",
        model_version="v",
        analyzed_at=_now(),
        entities=[ticker],
        industries=["Tech"],
        channels=["c"],
        evidence=["e"],
    )
    session.add(ev)
    session.commit()
    return inst, ev


class TestGenerateAlerts:
    def _stub_sig(self, monkeypatch, rows):
        monkeypatch.setattr(alerting, "compute_event_type_significance", lambda s: rows)

    def test_creates_alert_for_watched_notable_event(self, session, monkeypatch):
        inst, ev = _seed_event(session, direction="positive")
        session.add(WatchlistItem(instrument_id=inst.id, created_at=_now()))
        session.commit()
        self._stub_sig(monkeypatch, [_sig("insider_trading", 5, -0.066)])

        created = generate_watchlist_alerts(session)
        assert created == 1
        alert = session.scalar(select(Alert))
        assert alert.event_id == ev.id
        assert alert.kind == "conflict"  # positive vs validated negative

    def test_idempotent(self, session, monkeypatch):
        inst, ev = _seed_event(session)
        session.add(WatchlistItem(instrument_id=inst.id, created_at=_now()))
        session.commit()
        self._stub_sig(monkeypatch, [_sig("insider_trading", 5, -0.066)])

        assert generate_watchlist_alerts(session) == 1
        assert generate_watchlist_alerts(session) == 0  # no duplicate
        assert session.scalar(select(Alert.event_id)) == ev.id

    def test_skips_unwatched_instruments(self, session, monkeypatch):
        _seed_event(session)  # not watched
        self._stub_sig(monkeypatch, [_sig("insider_trading", 5, -0.066)])
        assert generate_watchlist_alerts(session) == 0

    def test_skips_non_notable_type(self, session, monkeypatch):
        inst, ev = _seed_event(session, event_type="earnings")
        session.add(WatchlistItem(instrument_id=inst.id, created_at=_now()))
        session.commit()
        self._stub_sig(monkeypatch, [_sig("earnings", 5, -0.02, significant=False)])
        assert generate_watchlist_alerts(session) == 0

    def test_empty_watchlist_noop(self, session, monkeypatch):
        _seed_event(session)
        # Should not even call significance when nothing is watched.
        self._stub_sig(monkeypatch, [_sig("insider_trading", 5, -0.066)])
        assert generate_watchlist_alerts(session) == 0


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

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


class TestWatchlistApi:
    def test_add_requires_auth(self, client, session):
        inst, _ = _seed_event(session)
        assert client.post(f"/watchlist/{inst.id}").status_code == 401

    def test_add_and_list(self, client, session, token, monkeypatch):
        inst, _ = _seed_event(session, ticker="005930")
        monkeypatch.setattr(alerting, "compute_event_type_significance", lambda s: [])
        r = client.post(
            f"/watchlist/{inst.id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 201
        assert r.json()["ticker"] == "005930"

        listed = client.get("/watchlist").json()
        assert [w["instrument_id"] for w in listed] == [inst.id]

    def test_add_unknown_instrument_404(self, client, token):
        r = client.post("/watchlist/9999", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    def test_remove(self, client, session, token):
        inst, _ = _seed_event(session)
        session.add(WatchlistItem(instrument_id=inst.id, created_at=_now()))
        session.commit()
        r = client.delete(
            f"/watchlist/{inst.id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 204
        assert client.get("/watchlist").json() == []


class TestAlertsApi:
    def _seed_alert(self, session, *, read=False, ticker=None):
        inst, ev = _seed_event(session, ticker=ticker)
        alert = Alert(
            instrument_id=inst.id,
            event_id=ev.id,
            kind="conflict",
            created_at=_now(),
            read_at=_now() if read else None,
        )
        session.add(alert)
        session.commit()
        return alert

    def test_list_and_unread_count(self, client, session):
        self._seed_alert(session, read=False, ticker="005930")
        alerts = client.get("/alerts").json()
        assert len(alerts) == 1
        assert alerts[0]["kind"] == "conflict"
        assert alerts[0]["primary_ticker"] == "005930"
        assert client.get("/alerts/unread-count").json()["count"] == 1

    def test_unread_only_filter(self, client, session):
        self._seed_alert(session, read=True)
        assert client.get("/alerts", params={"unread_only": True}).json() == []

    def test_mark_read_requires_auth(self, client, session):
        alert = self._seed_alert(session)
        assert client.post(f"/alerts/{alert.id}/read").status_code == 401

    def test_mark_read(self, client, session, token):
        alert = self._seed_alert(session)
        r = client.post(
            f"/alerts/{alert.id}/read", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 204
        assert client.get("/alerts/unread-count").json()["count"] == 0

    def test_read_all(self, client, session, token):
        self._seed_alert(session)
        self._seed_alert(session)  # second instrument/event
        r = client.post(
            "/alerts/read-all", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 204
        assert client.get("/alerts/unread-count").json()["count"] == 0
