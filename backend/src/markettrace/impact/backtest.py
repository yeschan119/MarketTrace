"""Walk-forward backtest of event-type abnormal returns (Phase 4 validation).

Direction A asks whether an event type's reaction is *predictable out of sample*,
not merely non-zero in hindsight. This module runs an expanding-window
walk-forward backtest with look-ahead strictly blocked:

For each event in chronological order, the expected abnormal return for its type
is estimated **only from earlier events of the same type** (the training set
grows as time advances). That estimate's sign is the position; the event's
realised abnormal return is the outcome. An event is added to its type's history
*after* it has been scored, so no prediction ever sees its own — or any future —
outcome. This is the blueprint's guard against look-ahead bias (§9).

Reported per horizon:

* ``hit_rate`` — out-of-sample directional accuracy (predicted sign vs realised).
* ``mean_strategy_return`` — mean of ``sign(predicted) * realised`` (the return of
  trading the signal), i.e. market/sector-adjusted abnormal return after costs=0.
* ``information_coefficient`` — Pearson correlation between predicted and realised
  abnormal returns across the out-of-sample predictions.

Pure function over records (trivially testable); a thin session helper pulls the
records from ``event_impacts`` joined to each event's filing date.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import Document, Event, EventImpact

__all__ = [
    "BacktestEvent",
    "BacktestResult",
    "run_walk_forward_backtest",
    "walk_forward_backtest",
]

# Minimum prior same-type observations before a type starts being predicted.
DEFAULT_MIN_TRAIN_PER_TYPE = 3


@dataclass(frozen=True)
class BacktestEvent:
    """One scored event: when it happened, its type, and its abnormal return."""

    occurred_at: datetime
    event_type: str
    abnormal_return: float | None


@dataclass(frozen=True)
class BacktestResult:
    """Out-of-sample summary for one horizon."""

    horizon_days: int
    min_train_per_type: int
    n_events: int  # events with a usable abnormal return
    n_predictions: int  # out-of-sample predictions actually made
    hit_rate: float | None
    mean_strategy_return: float | None
    information_coefficient: float | None


def _sign(x: float) -> int:
    if x > 0.0:
        return 1
    if x < 0.0:
        return -1
    return 0


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0.0 or syy <= 0.0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return sxy / sqrt(sxx * syy)


def walk_forward_backtest(
    events: Iterable[BacktestEvent],
    *,
    horizon_days: int,
    min_train_per_type: int = DEFAULT_MIN_TRAIN_PER_TYPE,
) -> BacktestResult:
    """Run the expanding-window walk-forward backtest over ``events``.

    ``events`` may be in any order; they are sorted by ``occurred_at`` here.
    Events without an abnormal return are dropped (they can be neither predicted
    nor scored). Ties in ``occurred_at`` keep input order (stable sort), which is
    conservative: a same-day event never trains on its same-day siblings.
    """
    usable = [e for e in events if e.abnormal_return is not None]
    usable.sort(key=lambda e: e.occurred_at)

    history: dict[str, list[float]] = {}
    predicted: list[float] = []
    realized: list[float] = []

    for event in usable:
        prior = history.get(event.event_type)
        if prior is not None and len(prior) >= min_train_per_type:
            predicted.append(sum(prior) / len(prior))
            realized.append(event.abnormal_return)  # type: ignore[arg-type]
        # Record the outcome only AFTER scoring -> no look-ahead.
        history.setdefault(event.event_type, []).append(event.abnormal_return)  # type: ignore[arg-type]

    directional = [
        (p, r) for p, r in zip(predicted, realized, strict=True) if _sign(p) != 0 and _sign(r) != 0
    ]
    hit_rate: float | None = None
    if directional:
        hits = sum(1 for p, r in directional if _sign(p) == _sign(r))
        hit_rate = hits / len(directional)

    mean_strategy_return: float | None = None
    if predicted:
        strategy_returns = [_sign(p) * r for p, r in zip(predicted, realized, strict=True)]
        mean_strategy_return = sum(strategy_returns) / len(strategy_returns)

    return BacktestResult(
        horizon_days=horizon_days,
        min_train_per_type=min_train_per_type,
        n_events=len(usable),
        n_predictions=len(predicted),
        hit_rate=hit_rate,
        mean_strategy_return=mean_strategy_return,
        information_coefficient=_pearson(predicted, realized),
    )


def run_walk_forward_backtest(
    session: Session,
    *,
    horizon_days: int,
    min_train_per_type: int = DEFAULT_MIN_TRAIN_PER_TYPE,
) -> BacktestResult:
    """Backtest one horizon from ``event_impacts`` ordered by each event's filing date."""
    rows = session.execute(
        select(
            Document.published_at,
            EventImpact.event_type,
            EventImpact.abnormal_return,
        )
        .join(Event, Event.id == EventImpact.event_id)
        .join(Document, Document.id == Event.document_id)
        .where(EventImpact.horizon_days == horizon_days)
    ).all()
    events = [
        BacktestEvent(occurred_at=r[0], event_type=r[1], abnormal_return=r[2]) for r in rows
    ]
    return walk_forward_backtest(
        events, horizon_days=horizon_days, min_train_per_type=min_train_per_type
    )
