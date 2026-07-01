"""Event-type reaction statistics.

Aggregates realised abnormal returns by ``(event_type, horizon_days)`` to answer
the blueprint's Phase-3 question: *what is the average reaction and its
dispersion for each kind of event?* The core is a pure function over records so
it is trivially testable; a thin session helper pulls the records from
``event_impacts``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import Document, Event, EventImpact, Instrument

__all__ = [
    "EventContribution",
    "EventTypeStat",
    "aggregate_reactions",
    "compute_event_type_statistics",
    "event_type_contributions",
]


@dataclass(frozen=True)
class EventTypeStat:
    """Summary statistics for one ``(event_type, horizon_days)`` bucket.

    Attributes
    ----------
    event_type:
        The event category, e.g. ``"earnings_beat"``.
    horizon_days:
        Trading-day horizon the abnormal returns were measured over.
    count:
        Number of non-null abnormal returns in the bucket.
    mean_abnormal_return:
        Arithmetic mean of the abnormal returns, or ``None`` when ``count == 0``.
    std_abnormal_return:
        Sample standard deviation (``ddof = 1``), or ``None`` when fewer than
        two observations are present.
    """

    event_type: str
    horizon_days: int
    count: int
    mean_abnormal_return: float | None
    std_abnormal_return: float | None


def aggregate_reactions(
    records: Iterable[tuple[str, int, float | None]],
) -> list[EventTypeStat]:
    """Aggregate ``(event_type, horizon_days, abnormal_return)`` triples.

    ``None`` abnormal returns are ignored (they do not contribute to the count,
    mean, or standard deviation). Buckets are returned sorted by
    ``event_type`` then ``horizon_days`` for stable output.
    """
    buckets: dict[tuple[str, int], list[float]] = {}
    for event_type, horizon_days, ar in records:
        key = (event_type, horizon_days)
        bucket = buckets.setdefault(key, [])
        if ar is not None:
            bucket.append(ar)

    stats: list[EventTypeStat] = []
    for (event_type, horizon_days), values in sorted(buckets.items()):
        stats.append(
            EventTypeStat(
                event_type=event_type,
                horizon_days=horizon_days,
                count=len(values),
                mean_abnormal_return=_mean(values),
                std_abnormal_return=_sample_std(values),
            )
        )
    return stats


def compute_event_type_statistics(session: Session) -> list[EventTypeStat]:
    """Aggregate abnormal returns from the ``event_impacts`` table."""
    rows = session.execute(
        select(
            EventImpact.event_type,
            EventImpact.horizon_days,
            EventImpact.abnormal_return,
        )
    ).all()
    return aggregate_reactions((r[0], r[1], r[2]) for r in rows)


@dataclass(frozen=True)
class EventContribution:
    """One event's contribution to an ``(event_type, horizon_days)`` statistic.

    Each :class:`EventTypeStat` mean is the average of the ``abnormal_return``
    values across every contribution sharing its ``(event_type, horizon_days)``.
    Surfacing these makes the statistic auditable: the user can see exactly which
    events — and which per-event returns — the aggregate was computed from.
    """

    event_id: int
    event_type: str
    horizon_days: int
    abnormal_return: float | None
    direction: str
    published_at: datetime
    primary_ticker: str | None
    instrument_name: str | None
    market: str | None


def event_type_contributions(session: Session) -> list[EventContribution]:
    """Per-event abnormal returns behind every event-type statistic.

    Joins ``event_impacts`` to each event's filing (for the date) and instrument
    (for ticker/name/market), newest filing first. The frontend filters these by
    ``(event_type, horizon_days)`` to show the events a given statistic aggregates.
    """
    rows = session.execute(
        select(
            EventImpact.event_id,
            EventImpact.event_type,
            EventImpact.horizon_days,
            EventImpact.abnormal_return,
            EventImpact.direction,
            Document.published_at,
            Instrument.ticker,
            Instrument.name,
            Instrument.market,
        )
        .join(Event, Event.id == EventImpact.event_id)
        .join(Document, Document.id == Event.document_id)
        .join(Instrument, Instrument.id == EventImpact.instrument_id)
        .order_by(Document.published_at.desc())
    ).all()
    return [
        EventContribution(
            event_id=r[0],
            event_type=r[1],
            horizon_days=r[2],
            abnormal_return=r[3],
            direction=r[4],
            published_at=r[5],
            primary_ticker=r[6],
            instrument_name=r[7],
            market=r[8],
        )
        for r in rows
    ]


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _sample_std(values: Sequence[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return sqrt(variance)
