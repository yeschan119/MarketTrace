"""Read-only API routes for MarketTrace."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.api.deps import get_db
from markettrace.api.schemas import (
    BacktestResultOut,
    CalibrationReportOut,
    DocumentOut,
    EventContributionOut,
    EventDetail,
    EventSummary,
    EventTypeSignificanceOut,
    EventTypeStatOut,
    InstrumentOut,
    InstrumentRankingOut,
    InstrumentTimeline,
    MacroObservationOut,
    MacroSeriesBacktestOut,
    OutcomeOut,
)
from markettrace.config import get_settings
from markettrace.db.models import (
    Document,
    Event,
    Instrument,
    MacroObservation,
    Outcome,
)
from markettrace.impact.backtest import (
    DEFAULT_MIN_TRAIN_PER_TYPE,
    run_macro_decomposition,
    run_walk_forward_backtest,
)
from markettrace.impact.calibration import compute_confidence_calibration
from markettrace.impact.instrument_ranking import (
    DEFAULT_HALF_LIFE_DAYS,
    RankingEventInput,
    rank_instruments,
)
from markettrace.impact.signal import SIGNAL_MODEL_NAMES, make_signal_model
from markettrace.impact.significance import compute_event_type_significance
from markettrace.impact.statistics import (
    compute_event_type_statistics,
    event_type_contributions,
)

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
        market=instrument.market if instrument else None,
        reviewed_at=event.reviewed_at,
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


def build_event_detail(db: Session, event: Event) -> EventDetail:
    """Assemble the full EventDetail payload for an event; 404 if its document
    is missing. Shared by the read route and the review (PATCH) route."""
    document = db.get(Document, event.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    outcomes_stmt = (
        select(Outcome)
        .where(Outcome.event_id == event.id)
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
        reviewed_at=event.reviewed_at,
        original_direction=event.original_direction,
        original_event_type=event.original_event_type,
        original_confidence=event.original_confidence,
        document=DocumentOut.model_validate(document),
        outcomes=[OutcomeOut.model_validate(o) for o in outcomes],
    )


@router.get("/events/{event_id}", response_model=EventDetail)
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventDetail:
    """Return full EventDetail for a single event; 404 if not found."""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return build_event_detail(db, event)


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


@router.get("/stats/event-types/contributions", response_model=list[EventContributionOut])
def get_event_type_contributions(
    db: Session = Depends(get_db),
) -> list[EventContributionOut]:
    """Per-event abnormal returns behind each (event_type, horizon) statistic.

    The frontend filters these by (event_type, horizon_days) to reveal exactly
    which events — and which returns — a given statistic's mean is computed from.
    """
    contributions = event_type_contributions(db)
    return [EventContributionOut.model_validate(c) for c in contributions]


@router.get("/stats/significance", response_model=list[EventTypeSignificanceOut])
def get_event_type_significance(
    db: Session = Depends(get_db),
) -> list[EventTypeSignificanceOut]:
    """Per (event_type, horizon) one-sample t-test: is the mean abnormal return
    distinguishable from zero, and is the sample even large enough to say?"""
    results = compute_event_type_significance(db)
    return [EventTypeSignificanceOut.model_validate(r) for r in results]


@router.get("/stats/instrument-ranking", response_model=list[InstrumentRankingOut])
def get_instrument_ranking(
    limit: int = 50,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    db: Session = Depends(get_db),
) -> list[InstrumentRankingOut]:
    """Rank instruments by confidence x recency weighted validated drift.

    Refines the single-instrument buy-judgment card into a cross-instrument
    comparison: each instrument's validated events are weighted by their LLM
    confidence and by recency (exponential decay, ``half_life_days``) before
    averaging their type's statistically-validated abnormal-return drift.
    Sorted ascending by score — strongest historical caution first. ``limit``
    caps the returned rows; ``half_life_days`` tunes how fast old events fade.
    """
    if half_life_days <= 0:
        raise HTTPException(status_code=400, detail="half_life_days must be positive")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")

    significance = compute_event_type_significance(db)

    stmt = (
        select(Event, Document)
        .join(Document, Event.document_id == Document.id)
        .where(Event.primary_instrument_id.is_not(None))
    )
    inputs: list[RankingEventInput] = []
    for event, document in db.execute(stmt).all():
        instrument = event.primary_instrument
        if instrument is None:
            continue
        inputs.append(
            RankingEventInput(
                instrument_id=instrument.id,
                ticker=instrument.ticker,
                name=instrument.name,
                market=instrument.market,
                event_type=event.event_type,
                direction=event.direction,
                confidence=event.confidence,
                published_at=document.published_at,
                reviewed_at=event.reviewed_at,
            )
        )

    ranked = rank_instruments(
        inputs, significance, date.today(), half_life_days=half_life_days
    )
    return [InstrumentRankingOut.model_validate(r) for r in ranked[:limit]]


@router.get("/stats/backtest", response_model=list[BacktestResultOut])
def get_backtest(
    model: str = "event_type_history", db: Session = Depends(get_db)
) -> list[BacktestResultOut]:
    """Walk-forward, look-ahead-blocked out-of-sample backtest per horizon:
    hit rate, gross and net-of-cost strategy return, and information coefficient.

    ``?model=`` selects the signal: ``event_type_history`` (default, learns each
    type's mean reaction) or ``llm_direction`` (trades the event's own direction).
    """
    if model not in SIGNAL_MODEL_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown model {model!r}; choose one of {list(SIGNAL_MODEL_NAMES)}",
        )
    settings = get_settings()
    results = [
        run_walk_forward_backtest(
            db,
            horizon_days=h,
            commission_per_trade=settings.backtest_commission_per_trade,
            slippage_per_trade=settings.backtest_slippage_per_trade,
            model=make_signal_model(model, min_train=DEFAULT_MIN_TRAIN_PER_TYPE),
        )
        for h in _BACKTEST_HORIZONS
    ]
    return [BacktestResultOut.model_validate(r) for r in results]


@router.get("/stats/macro-decomposition", response_model=list[MacroSeriesBacktestOut])
def get_macro_decomposition(
    db: Session = Depends(get_db),
) -> list[MacroSeriesBacktestOut]:
    """Per-macro-series walk-forward backtest: which series (if any) carries the edge.

    Decomposes the composite ``macro_surprise`` model — which conditions on the
    freshest surprise across all series — into one standalone backtest per series
    and horizon, so a strong composite IC can be attributed rather than taken on
    faith (it may be one series, or merely a slow calendar proxy)."""
    settings = get_settings()
    results = run_macro_decomposition(
        db,
        horizons=_BACKTEST_HORIZONS,
        min_train_per_type=DEFAULT_MIN_TRAIN_PER_TYPE,
        commission_per_trade=settings.backtest_commission_per_trade,
        slippage_per_trade=settings.backtest_slippage_per_trade,
    )
    return [MacroSeriesBacktestOut.model_validate(r) for r in results]


@router.get("/stats/calibration", response_model=list[CalibrationReportOut])
def get_calibration(db: Session = Depends(get_db)) -> list[CalibrationReportOut]:
    """Reliability of the LLM ``confidence`` as a directional-hit probability, per horizon.

    For each horizon, bins directional predictions by their stated confidence and
    compares the mean confidence in each bin to the observed hit rate, plus a
    sample-weighted Expected Calibration Error and Brier score. Answers the
    blueprint §8 bar: does a confidence of 0.7 actually hit ~70%?"""
    reports = compute_confidence_calibration(db, horizons=_BACKTEST_HORIZONS)
    return [CalibrationReportOut.model_validate(r) for r in reports]


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
