"""Read-only API routes for MarketTrace."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.api.deps import get_db
from markettrace.api.schemas import (
    BacktestResultOut,
    DocumentOut,
    EventDetail,
    EventSummary,
    EventTypeSignificanceOut,
    EventTypeStatOut,
    InstrumentOut,
    InstrumentTimeline,
    MacroObservationOut,
    OutcomeOut,
)
from markettrace.db.models import (
    Document,
    Event,
    Instrument,
    MacroObservation,
    Outcome,
)
from markettrace.impact.backtest import run_walk_forward_backtest
from markettrace.impact.significance import compute_event_type_significance
from markettrace.impact.statistics import compute_event_type_statistics

# Standard event-study horizons (trading days) reported by the backtest.
_BACKTEST_HORIZONS = (1, 5, 20, 60)

router = APIRouter()


def _event_summary(event: Event, document: Document) -> EventSummary:
    """Build an EventSummary from an ORM Event and its Document."""
    instrument = event.primary_instrument
    return EventSummary(
        id=event.id,
        event_type=event.event_type,
        direction=event.direction,
        confidence=event.confidence,
        published_at=document.published_at,
        primary_ticker=instrument.ticker if instrument else None,
        instrument_name=instrument.name if instrument else None,
    )


@router.get("/events", response_model=list[EventSummary])
def list_events(db: Session = Depends(get_db)) -> list[EventSummary]:
    """Return all events sorted by document.published_at descending."""
    stmt = (
        select(Event, Document)
        .join(Document, Event.document_id == Document.id)
        .order_by(Document.published_at.desc())
    )
    rows = db.execute(stmt).all()
    return [_event_summary(event, doc) for event, doc in rows]


@router.get("/events/{event_id}", response_model=EventDetail)
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventDetail:
    """Return full EventDetail for a single event; 404 if not found."""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    document = db.get(Document, event.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    outcomes_stmt = (
        select(Outcome)
        .where(Outcome.event_id == event_id)
        .order_by(Outcome.horizon_days.asc())
    )
    outcomes = db.scalars(outcomes_stmt).all()

    return EventDetail(
        id=event.id,
        event_type=event.event_type,
        entities=list(event.entities) if event.entities else [],
        industries=list(event.industries) if event.industries else [],
        channels=list(event.channels) if event.channels else [],
        direction=event.direction,
        horizon_days=event.horizon_days,
        confidence=event.confidence,
        surprise_score=event.surprise_score,
        novelty_score=event.novelty_score,
        source_reliability=event.source_reliability,
        evidence=list(event.evidence) if event.evidence else [],
        model=event.model,
        model_version=event.model_version,
        document=DocumentOut.model_validate(document),
        outcomes=[OutcomeOut.model_validate(o) for o in outcomes],
    )


@router.get("/instruments/{instrument_id}/timeline", response_model=InstrumentTimeline)
def get_instrument_timeline(
    instrument_id: int, db: Session = Depends(get_db)
) -> InstrumentTimeline:
    """Return instrument + events where primary_instrument_id matches; 404 if missing."""
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")

    stmt = (
        select(Event, Document)
        .join(Document, Event.document_id == Document.id)
        .where(Event.primary_instrument_id == instrument_id)
        .order_by(Document.published_at.desc())
    )
    rows = db.execute(stmt).all()

    return InstrumentTimeline(
        instrument=InstrumentOut.model_validate(instrument),
        events=[_event_summary(event, doc) for event, doc in rows],
    )


@router.get("/stats/event-types", response_model=list[EventTypeStatOut])
def get_event_type_stats(db: Session = Depends(get_db)) -> list[EventTypeStatOut]:
    """Mean and dispersion of abnormal returns per (event_type, horizon)."""
    stats = compute_event_type_statistics(db)
    return [EventTypeStatOut.model_validate(s) for s in stats]


@router.get("/stats/significance", response_model=list[EventTypeSignificanceOut])
def get_event_type_significance(
    db: Session = Depends(get_db),
) -> list[EventTypeSignificanceOut]:
    """Per (event_type, horizon) one-sample t-test: is the mean abnormal return
    distinguishable from zero, and is the sample even large enough to say?"""
    results = compute_event_type_significance(db)
    return [EventTypeSignificanceOut.model_validate(r) for r in results]


@router.get("/stats/backtest", response_model=list[BacktestResultOut])
def get_backtest(db: Session = Depends(get_db)) -> list[BacktestResultOut]:
    """Walk-forward, look-ahead-blocked out-of-sample backtest per horizon:
    hit rate, mean strategy return, and information coefficient."""
    results = [run_walk_forward_backtest(db, horizon_days=h) for h in _BACKTEST_HORIZONS]
    return [BacktestResultOut.model_validate(r) for r in results]


@router.get("/macro/observations", response_model=list[MacroObservationOut])
def get_macro_observations(
    series: str | None = None, db: Session = Depends(get_db)
) -> list[MacroObservationOut]:
    """Latest macro release (with surprise) per series, sorted by series id.

    Optional ``?series=CPIAUCSL,UNRATE`` filters to the given comma-separated
    series ids. Returns one row per series — the most recent reference period
    (and revision) on record.
    """
    stmt = select(MacroObservation)
    if series:
        wanted = [s.strip() for s in series.split(",") if s.strip()]
        stmt = stmt.where(MacroObservation.series_id.in_(wanted))
    rows = db.scalars(stmt).all()

    latest: dict[str, MacroObservation] = {}
    for row in rows:
        current = latest.get(row.series_id)
        if current is None or (row.reference_date, row.revision) > (
            current.reference_date,
            current.revision,
        ):
            latest[row.series_id] = row

    return [
        MacroObservationOut.model_validate(latest[k]) for k in sorted(latest)
    ]
