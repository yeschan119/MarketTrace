"""Build per-event impact rows from computed outcomes.

An :class:`~markettrace.db.models.EventImpact` is the scored layer above a raw
:class:`~markettrace.db.models.Outcome`: it folds the event's stated
``direction`` into the abnormal return so downstream aggregation can tell a
*confirmed* reaction (direction agrees with the realised abnormal return) from a
*contradicted* one.
"""

from __future__ import annotations

from datetime import datetime

from markettrace.db.models import Event, EventImpact
from markettrace.impact.returns import OutcomeResult

__all__ = ["direction_sign", "build_event_impacts"]

# Map an event direction string to a multiplier applied to the abnormal return.
_DIRECTION_SIGN: dict[str, int] = {"positive": 1, "negative": -1, "neutral": 0}


def direction_sign(direction: str) -> int:
    """Return ``+1`` / ``-1`` / ``0`` for a ``positive`` / ``negative`` / other direction."""
    return _DIRECTION_SIGN.get(direction, 0)


def build_event_impacts(
    event: Event,
    outcomes: list[OutcomeResult],
    *,
    industry: str | None,
    computed_at: datetime,
) -> list[EventImpact]:
    """Create one :class:`EventImpact` per outcome horizon for *event*.

    ``signed_abnormal_return`` is ``abnormal_return * direction_sign(direction)``:
    positive when the realised abnormal return moved in the event's predicted
    direction, negative when it moved against it, and ``None`` when the abnormal
    return itself is unavailable. Neutral-direction events get ``0.0``.

    Rows are returned (not added to any session) so the caller controls
    persistence and transaction boundaries.
    """
    sign = direction_sign(event.direction)
    impacts: list[EventImpact] = []

    for o in outcomes:
        if o.abnormal_return is None:
            signed: float | None = None
        else:
            signed = o.abnormal_return * sign

        impacts.append(
            EventImpact(
                event_id=event.id,
                instrument_id=event.primary_instrument_id,
                event_type=event.event_type,
                industry=industry,
                direction=event.direction,
                horizon_days=o.horizon_days,
                abnormal_return=o.abnormal_return,
                sector_abnormal_return=o.sector_abnormal_return,
                signed_abnormal_return=signed,
                computed_at=computed_at,
            )
        )

    return impacts
