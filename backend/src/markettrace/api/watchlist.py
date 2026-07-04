"""Watchlist + in-app alerts API (Phase 5).

Reads are public (alerts are derived from public event data); mutations —
adding/removing a watched instrument, marking alerts read — require the admin
auth used by the rest of the write surface. Adding an instrument immediately
runs :func:`generate_watchlist_alerts` so the just-watched stock's notable
events surface right away, without waiting for the next ingest.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from markettrace.api.auth import require_auth
from markettrace.api.deps import get_db
from markettrace.api.schemas import AlertOut, UnreadCountOut, WatchlistItemOut
from markettrace.db.models import (
    Alert,
    Document,
    Event,
    Instrument,
    WatchlistItem,
)
from markettrace.impact.alerting import generate_watchlist_alerts

router = APIRouter()


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

@router.get("/watchlist", response_model=list[WatchlistItemOut])
def list_watchlist(db: Session = Depends(get_db)) -> list[WatchlistItemOut]:
    """Return the watched instruments, most recently added first."""
    rows = db.execute(
        select(Instrument, WatchlistItem.created_at)
        .join(WatchlistItem, WatchlistItem.instrument_id == Instrument.id)
        .order_by(WatchlistItem.created_at.desc())
    ).all()
    return [
        WatchlistItemOut(
            instrument_id=inst.id,
            ticker=inst.ticker,
            name=inst.name,
            market=inst.market,
            created_at=created_at,
        )
        for inst, created_at in rows
    ]


@router.post("/watchlist/{instrument_id}", status_code=201, response_model=WatchlistItemOut)
def add_watchlist(
    instrument_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
) -> WatchlistItemOut:
    """Watch an instrument (idempotent) and generate any alerts for it now."""
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="instrument not found")

    existing = db.scalar(
        select(WatchlistItem).where(WatchlistItem.instrument_id == instrument_id)
    )
    if existing is None:
        db.add(WatchlistItem(instrument_id=instrument_id, created_at=datetime.now(UTC)))
        db.commit()
        # Surface the just-watched instrument's notable events immediately.
        generate_watchlist_alerts(db)
        existing = db.scalar(
            select(WatchlistItem).where(WatchlistItem.instrument_id == instrument_id)
        )

    return WatchlistItemOut(
        instrument_id=instrument.id,
        ticker=instrument.ticker,
        name=instrument.name,
        market=instrument.market,
        created_at=existing.created_at,
    )


@router.delete("/watchlist/{instrument_id}", status_code=204)
def remove_watchlist(
    instrument_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
) -> None:
    """Unwatch an instrument (idempotent). Existing alerts are kept."""
    db.execute(delete(WatchlistItem).where(WatchlistItem.instrument_id == instrument_id))
    db.commit()


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def _alert_out(alert: Alert, event: Event, document: Document) -> AlertOut:
    instrument = event.primary_instrument
    return AlertOut(
        id=alert.id,
        kind=alert.kind,
        created_at=alert.created_at,
        read_at=alert.read_at,
        event_id=event.id,
        event_type=event.event_type,
        direction=event.direction,
        primary_ticker=instrument.ticker if instrument else None,
        instrument_name=instrument.name if instrument else None,
        market=instrument.market if instrument else None,
        published_at=document.published_at,
    )


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    db: Session = Depends(get_db),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AlertOut]:
    """Return alerts, unread first then newest first."""
    stmt = (
        select(Alert, Event, Document)
        .join(Event, Alert.event_id == Event.id)
        .join(Document, Event.document_id == Document.id)
        .order_by(Alert.read_at.is_(None).desc(), Alert.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Alert.read_at.is_(None))
    rows = db.execute(stmt).all()
    return [_alert_out(alert, event, doc) for alert, event, doc in rows]


@router.get("/alerts/unread-count", response_model=UnreadCountOut)
def unread_count(db: Session = Depends(get_db)) -> UnreadCountOut:
    """Return the number of unread alerts (for the header bell badge)."""
    count = db.scalar(
        select(func.count()).select_from(Alert).where(Alert.read_at.is_(None))
    )
    return UnreadCountOut(count=count or 0)


@router.post("/alerts/{alert_id}/read", status_code=204)
def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
) -> None:
    """Mark one alert read (idempotent; 404 if it does not exist)."""
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    if alert.read_at is None:
        alert.read_at = datetime.now(UTC)
        db.commit()


@router.post("/alerts/read-all", status_code=204)
def mark_all_read(
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
) -> None:
    """Mark every unread alert read."""
    now = datetime.now(UTC)
    db.query(Alert).filter(Alert.read_at.is_(None)).update(
        {Alert.read_at: now}, synchronize_session=False
    )
    db.commit()
