"""Watchlist alert generation — decide when a watched event is worth notifying.

The trigger mirrors the frontend ``assessSignal`` verdict so in-app alerts agree
with the validated-signal badges shown on the event pages: an event is *notable*
only when its ``event_type`` is a statistically validated (significant, adequate
sample) bucket. Among those, the alert is a ``"conflict"`` when the model's
stated direction opposes the validated historical drift, otherwise a plain
``"significant"`` heads-up.

Everything here is a pure function of the significance table + the event's
(direction, event_type, horizon), so the same logic runs at ingest time in the
backend without importing any frontend code.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import Alert, Event, WatchlistItem
from markettrace.impact.significance import (
    EventTypeSignificance,
    compute_event_type_significance,
)

__all__ = ["assess_event_alert", "generate_watchlist_alerts"]

# Alert kinds, most-urgent first (used only for documentation/ordering).
CONFLICT = "conflict"
SIGNIFICANT = "significant"


def _hist_dir(mean: float | None) -> str | None:
    """Validated mean abnormal return -> 'up' / 'down' / None (mirrors histDir)."""
    if mean is None or mean == 0:
        return None
    return "up" if mean > 0 else "down"


def _llm_dir(direction: str) -> str | None:
    """Model direction -> 'up' / 'down' / None (mirrors llmDir)."""
    k = (direction or "").lower()
    if k == "positive":
        return "up"
    if k == "negative":
        return "down"
    return None


def assess_event_alert(
    *,
    direction: str,
    event_type: str,
    horizon_days: int,
    significance: list[EventTypeSignificance],
) -> str | None:
    """Return the alert kind for an event, or ``None`` when it is not notable.

    Mirrors the frontend ``assessSignal`` headline selection: filter to the
    event type's significant, adequately-sampled rows; pick the row matching the
    event's own horizon, else the lowest-p-value row. An event whose type has no
    such row is not notable (``None``). Otherwise it is ``"conflict"`` when the
    model direction opposes the validated drift, else ``"significant"``.
    """
    rows = [
        r
        for r in significance
        if r.event_type == event_type and r.significant_5pct and r.sufficient_sample
    ]
    if not rows:
        return None

    headline = next((r for r in rows if r.horizon_days == horizon_days), None)
    if headline is None:
        headline = min(rows, key=lambda r: r.p_value if r.p_value is not None else 1.0)

    hd = _hist_dir(headline.mean_abnormal_return)
    if hd is None:
        return None

    ld = _llm_dir(direction)
    if ld is not None and ld != hd:
        return CONFLICT
    return SIGNIFICANT


def generate_watchlist_alerts(session: Session, *, now: datetime | None = None) -> int:
    """Create alerts for notable, not-yet-alerted events on watched instruments.

    Idempotent: an event with an existing alert is skipped (``alerts.event_id``
    is unique), so re-running never duplicates. Returns the number of new alerts
    created. When the watchlist is empty this is a cheap no-op.
    """
    now = now or datetime.now(UTC)

    watched = set(session.scalars(select(WatchlistItem.instrument_id)).all())
    if not watched:
        return 0

    already = set(session.scalars(select(Alert.event_id)).all())
    significance = compute_event_type_significance(session)

    events = session.scalars(
        select(Event).where(Event.primary_instrument_id.in_(watched))
    ).all()

    created = 0
    for event in events:
        if event.id in already:
            continue
        kind = assess_event_alert(
            direction=event.direction,
            event_type=event.event_type,
            horizon_days=event.horizon_days,
            significance=significance,
        )
        if kind is None:
            continue
        session.add(
            Alert(
                instrument_id=event.primary_instrument_id,
                event_id=event.id,
                kind=kind,
                created_at=now,
            )
        )
        created += 1

    if created:
        session.commit()
    return created
