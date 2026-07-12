"""Write routes for human review of LLM-extracted events (Phase 2).

The rest of the API is read-only; this module is the one place an authenticated
admin can correct an extraction. A ``direction`` or ``event_type`` edit rebuilds
the event's :class:`EventImpact` rows so every downstream aggregate
(``/stats/*`` significance, backtest, calibration) reflects the correction. The
rebuild reuses the stored :class:`Outcome` rows — no price data is re-fetched,
since abnormal returns are independent of the (human-editable) direction.

Correcting a mis-linked company is different: abnormal returns depend on that
instrument's price series, so ``primary_instrument_id`` edits re-fetch prices
and recompute outcomes + impacts in the same transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.api.auth import require_auth
from markettrace.api.deps import get_db, get_price_provider_factory
from markettrace.api.routes import build_event_detail
from markettrace.api.schemas import EventDetail, EventUpdate
from markettrace.config import get_settings
from markettrace.db.models import DocumentEntity, Event, EventImpact, Instrument, Outcome
from markettrace.impact.event_impacts import build_event_impacts
from markettrace.impact.returns import OutcomeResult
from markettrace.pipeline.vertical_slice import recompute_event_outcomes

router = APIRouter()

_VALID_DIRECTIONS = {"positive", "negative", "neutral"}


def _rebuild_impacts(db: Session, event: Event, *, computed_at: datetime) -> None:
    """Recompute the event's impact rows from its stored outcomes.

    No-op when the event has no primary instrument (impacts require one) or no
    outcomes yet. The industry snapshot is preserved from the existing impact
    rows, falling back to the instrument's current sector.
    """
    if event.primary_instrument_id is None:
        return

    existing = db.scalars(
        select(EventImpact).where(EventImpact.event_id == event.id)
    ).all()
    industry = existing[0].industry if existing else None
    if industry is None and event.primary_instrument is not None:
        industry = event.primary_instrument.industry

    for impact in existing:
        db.delete(impact)

    outcomes = db.scalars(
        select(Outcome)
        .where(Outcome.event_id == event.id)
        .order_by(Outcome.horizon_days.asc())
    ).all()
    if not outcomes:
        return

    results = [
        OutcomeResult(
            horizon_days=o.horizon_days,
            raw_return=o.raw_return,
            market_return=o.market_return,
            abnormal_return=o.abnormal_return,
            sector_return=o.sector_return,
            sector_abnormal_return=o.sector_abnormal_return,
        )
        for o in outcomes
    ]
    db.flush()  # apply deletes before re-inserting (unique event_id+horizon)
    for impact in build_event_impacts(
        event, results, industry=industry, computed_at=computed_at
    ):
        db.add(impact)


def _market_index_ticker(market: str | None) -> str:
    """Return the benchmark ticker for a market during outcome recomputation."""
    if market is not None and market.upper() == "KR":
        return get_settings().kr_market_index_ticker
    return "spy"


def _ensure_document_entity(db: Session, event: Event, instrument: Instrument) -> None:
    """Ensure the reviewed document has an entity link to the corrected company."""
    existing = db.scalar(
        select(DocumentEntity).where(
            DocumentEntity.document_id == event.document_id,
            DocumentEntity.instrument_id == instrument.id,
        )
    )
    if existing is None:
        db.add(
            DocumentEntity(
                document_id=event.document_id,
                instrument_id=instrument.id,
                confidence=1.0,
            )
        )
    else:
        existing.confidence = max(existing.confidence, 1.0)


@router.patch("/events/{event_id}", response_model=EventDetail)
def review_event(
    event_id: int,
    payload: EventUpdate,
    db: Session = Depends(get_db),
    price_provider_factory: Callable[[str], object] = Depends(get_price_provider_factory),
    _: None = Depends(require_auth),
) -> EventDetail:
    """Apply human corrections to an event and return the updated detail.

    On the first review the model's original values are snapshotted into
    ``original_*``. Impacts are rebuilt when ``direction`` or ``event_type``
    changes. A ``primary_instrument_id`` edit recomputes outcomes and impacts
    against the corrected company.
    """
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if payload.direction is not None and payload.direction not in _VALID_DIRECTIONS:
        raise HTTPException(status_code=422, detail="Invalid direction")
    if payload.confidence is not None and not (0.0 <= payload.confidence <= 1.0):
        raise HTTPException(status_code=422, detail="confidence must be in [0, 1]")
    if payload.event_type is not None and not payload.event_type.strip():
        raise HTTPException(status_code=422, detail="event_type must not be empty")

    new_instrument: Instrument | None = None
    if (
        payload.primary_instrument_id is not None
        and payload.primary_instrument_id != event.primary_instrument_id
    ):
        new_instrument = db.get(Instrument, payload.primary_instrument_id)
        if new_instrument is None:
            raise HTTPException(status_code=422, detail="Instrument not found")

    # Snapshot the model's values once, on the first manual edit.
    if event.reviewed_at is None:
        event.original_direction = event.direction
        event.original_event_type = event.event_type
        event.original_confidence = event.confidence
        event.original_primary_instrument_id = event.primary_instrument_id
    elif new_instrument is not None and event.original_primary_instrument_id is None:
        event.original_primary_instrument_id = event.primary_instrument_id

    impact_dirty = False
    if payload.direction is not None and payload.direction != event.direction:
        event.direction = payload.direction
        impact_dirty = True
    if payload.event_type is not None and payload.event_type != event.event_type:
        event.event_type = payload.event_type
        impact_dirty = True
    if payload.confidence is not None:
        event.confidence = payload.confidence
    if new_instrument is not None:
        event.primary_instrument_id = new_instrument.id
        event.primary_instrument = new_instrument
        event.entities = [new_instrument.ticker]
        _ensure_document_entity(db, event, new_instrument)

    now = datetime.now(UTC)
    event.reviewed_at = now

    if new_instrument is not None:
        try:
            recompute_event_outcomes(
                db,
                event=event,
                instrument=new_instrument,
                price_provider=price_provider_factory(new_instrument.market),
                market_index_ticker=_market_index_ticker(new_instrument.market),
            )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - external price provider boundary
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail="price fetch failed while recomputing outcomes for the new instrument",
            ) from exc
    elif impact_dirty:
        _rebuild_impacts(db, event, computed_at=now)

    db.commit()
    db.refresh(event)
    return build_event_detail(db, event)
