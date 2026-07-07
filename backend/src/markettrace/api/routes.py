"""Read-only API routes for MarketTrace."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from markettrace.api.deps import get_db
from markettrace.api.schemas import (
    BacktestResultOut,
    CalibrationReportOut,
    DocumentOut,
    DrawdownScreenerOut,
    EventContributionOut,
    EventDetail,
    EventSummary,
    EventTypeSignificanceOut,
    EventTypeStatOut,
    InstrumentOut,
    InstrumentRankingOut,
    InstrumentSearchOut,
    InstrumentTimeline,
    MacroObservationOut,
    MacroSeriesBacktestOut,
    OutcomeOut,
    TopFactorOut,
)
from markettrace.config import get_settings
from markettrace.db.models import (
    Document,
    EntityAlias,
    Event,
    Instrument,
    MacroObservation,
    Outcome,
    Price,
)
from markettrace.impact.backtest import (
    DEFAULT_MIN_TRAIN_PER_TYPE,
    run_macro_decomposition,
    run_walk_forward_backtest,
)
from markettrace.impact.calibration import compute_confidence_calibration
from markettrace.impact.drawdown import (
    DEFAULT_WINDOW,
    PricePoint,
    classify_drop,
    compute_drawdown,
)
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
        primary_instrument_id=instrument.id if instrument else None,
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


# Max rows returned by the search entry point regardless of the requested limit.
_SEARCH_MAX_LIMIT = 50


@router.get("/instruments/search", response_model=list[InstrumentSearchOut])
def search_instruments(
    q: str, limit: int = 20, db: Session = Depends(get_db)
) -> list[InstrumentSearchOut]:
    """Case-insensitive instrument search over ticker, name, and aliases.

    Powers the search-box entry point into the per-instrument analysis view.
    Results are ordered by how many events reference the instrument (most
    covered first) so the richest analyses surface at the top.
    """
    query = q.strip()
    if not query:
        return []
    capped = max(1, min(limit, _SEARCH_MAX_LIMIT))
    like = f"%{query}%"
    alias_ids = select(EntityAlias.instrument_id).where(EntityAlias.alias.ilike(like))
    event_count = func.count(Event.id)
    stmt = (
        select(Instrument, event_count)
        .outerjoin(Event, Event.primary_instrument_id == Instrument.id)
        .where(
            or_(
                Instrument.ticker.ilike(like),
                Instrument.name.ilike(like),
                Instrument.id.in_(alias_ids),
            )
        )
        .group_by(Instrument.id)
        .order_by(event_count.desc(), Instrument.ticker.asc())
        .limit(capped)
    )
    rows = db.execute(stmt).all()
    return [
        InstrumentSearchOut(
            id=inst.id,
            ticker=inst.ticker,
            name=inst.name,
            market=inst.market,
            industry=inst.industry,
            event_count=count,
        )
        for inst, count in rows
    ]


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


@router.get("/stats/drawdown-screener", response_model=list[DrawdownScreenerOut])
def get_drawdown_screener(
    threshold: float = -0.15,
    window: int = DEFAULT_WINDOW,
    max_stale_days: int = 5,
    recent_days: int = 30,
    include_stale: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[DrawdownScreenerOut]:
    """Screen sharply-fallen instruments and diagnose each against event history.

    Feature 1: of the names down hard, which fall is *explained* by validated
    negative-drift events (``persistent_risk``), which has *no* event basis in
    our data (``unexplained_drop``), and which dropped despite a non-negative
    validated basis (``possible_overreaction`` — a rebound *candidate* pending
    the mean-reversion backtest, never a buy call).

    Drawdown is measured from the trailing ``window`` trading-day high on adjusted
    closes. Only instruments down at least ``threshold`` (e.g. -0.15) are
    returned. Prices here are refreshed by ``markettrace-refresh-prices``; an
    instrument whose latest bar is older than ``max_stale_days`` is flagged
    ``is_stale`` and excluded unless ``include_stale`` is set (a stale drawdown
    does not describe *today*). Sorted by drawdown ascending (deepest first).
    """
    if window < 1:
        raise HTTPException(status_code=400, detail="window must be positive")
    if threshold > 0:
        raise HTTPException(status_code=400, detail="threshold must be <= 0")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")

    today = date.today()
    recent_cutoff = today - timedelta(days=recent_days)

    # Validated event context, reused from the instrument ranking so the drop
    # diagnosis rests on the same significance gate as the rest of the app.
    significance = compute_event_type_significance(db)
    rank_stmt = (
        select(Event, Document)
        .join(Document, Event.document_id == Document.id)
        .where(Event.primary_instrument_id.is_not(None))
    )
    inputs: list[RankingEventInput] = []
    recent_event_counts: dict[int, int] = {}
    for event, document in db.execute(rank_stmt).all():
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
        if document.published_at.date() >= recent_cutoff:
            recent_event_counts[instrument.id] = (
                recent_event_counts.get(instrument.id, 0) + 1
            )

    ranked_by_id = {
        r.instrument_id: r
        for r in rank_instruments(inputs, significance, today)
    }

    rows: list[DrawdownScreenerOut] = []
    instruments = db.scalars(
        select(Instrument).where(Instrument.delisted_at.is_(None))
    ).all()
    for inst in instruments:
        price_rows = db.execute(
            select(Price.date, Price.adj_close)
            .where(Price.instrument_id == inst.id)
            .order_by(Price.date.desc())
            .limit(window)
        ).all()
        result = compute_drawdown(
            [PricePoint(date=d, adj_close=ac) for d, ac in price_rows],
            window=window,
        )
        if result is None or result.drawdown > threshold:
            continue

        is_stale = (today - result.latest_date).days > max_stale_days
        if is_stale and not include_stale:
            continue

        recent_count = recent_event_counts.get(inst.id, 0)
        rk = ranked_by_id.get(inst.id)
        rows.append(
            DrawdownScreenerOut(
                instrument_id=inst.id,
                ticker=inst.ticker,
                name=inst.name,
                market=inst.market,
                drawdown=result.drawdown,
                current_price=result.current_price,
                current_date=result.current_date,
                high_price=result.high_price,
                high_date=result.high_date,
                latest_date=result.latest_date,
                is_stale=is_stale,
                recent_event_count=recent_count,
                lean=rk.lean if rk else None,
                weighted_score=rk.weighted_score if rk else None,
                validated_count=rk.validated_count if rk else 0,
                top_factor=(
                    TopFactorOut.model_validate(rk.top_factor)
                    if rk and rk.top_factor
                    else None
                ),
                diagnosis=classify_drop(rk.lean if rk else None, recent_count),
            )
        )

    rows.sort(key=lambda r: r.drawdown)
    return rows[:limit]


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
