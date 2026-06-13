"""Smoke test: models round-trip on SQLite, including JSON columns."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import Document, Event, Instrument, Outcome


def test_models_round_trip(db_session: Session) -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)

    instrument = Instrument(market="US", ticker="AAPL", name="Apple Inc.", industry="Tech")
    document = Document(
        source="sec_edgar",
        external_id="0000320193-26-000001",
        url="https://www.sec.gov/example",
        content_hash="deadbeef",
        market="US",
        published_at=now,
        first_seen_at=now,
        occurred_at=now,
    )
    db_session.add_all([instrument, document])
    db_session.flush()

    event = Event(
        document_id=document.id,
        event_type="earnings",
        entities=[{"ticker": "AAPL", "role": "primary"}],
        industries=["Technology"],
        channels={"revenue": "up"},
        direction="positive",
        horizon_days=20,
        confidence=0.91,
        evidence=[{"quote": "record revenue", "url": document.url}],
        model="claude-sonnet-4-6",
        model_version="2026-06-01",
        analyzed_at=now,
    )
    db_session.add(event)
    db_session.flush()

    outcome = Outcome(
        event_id=event.id,
        instrument_id=instrument.id,
        horizon_days=5,
        raw_return=0.03,
        market_return=0.01,
        abnormal_return=0.02,
        computed_at=now,
    )
    db_session.add(outcome)
    db_session.commit()

    fetched = db_session.execute(
        select(Event).where(Event.id == event.id)
    ).scalar_one()

    # JSON columns round-trip with their native Python shapes.
    assert fetched.entities == [{"ticker": "AAPL", "role": "primary"}]
    assert fetched.industries == ["Technology"]
    assert fetched.channels == {"revenue": "up"}
    assert fetched.evidence[0]["quote"] == "record revenue"
    assert fetched.model == "claude-sonnet-4-6"

    fetched_outcome = db_session.execute(
        select(Outcome).where(Outcome.event_id == event.id)
    ).scalar_one()
    assert fetched_outcome.abnormal_return == 0.02

    # The instrument's relationships load without error.
    assert fetched.id == event.id
    assert instrument.prices == []
    assert isinstance(date(2026, 6, 12), date)
