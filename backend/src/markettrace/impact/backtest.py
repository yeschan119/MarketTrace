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
* ``mean_strategy_return`` — mean of ``sign(predicted) * realised`` (the *gross*
  return of trading the signal), i.e. market/sector-adjusted abnormal return
  before trading frictions.
* ``mean_strategy_return_net`` — the same after subtracting a round-trip trading
  cost (commission + slippage) from every position the strategy actually enters
  (``sign(predicted) != 0``). This is the blueprint's "거래 현실 반영" (§7-4):
  a signal is only worth trading if it survives costs.
* ``information_coefficient`` — Pearson correlation between predicted and realised
  abnormal returns across the out-of-sample predictions.

Coverage is reported honestly: events whose abnormal return is missing — a stock
that was delisted or halted over the horizon has no realised return — are counted
in ``n_dropped_no_outcome`` rather than silently vanishing, so a shrinking usable
sample is visible rather than mistaken for a clean one.

Pure function over records (trivially testable); a thin session helper pulls the
records from ``event_impacts`` joined to each event's filing date.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from math import sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import Document, Event, EventImpact, MacroObservation, Price
from markettrace.impact.signal import EventTypeSignal, MacroSurpriseSignal, SignalModel

__all__ = [
    "BacktestEvent",
    "BacktestResult",
    "MacroSeriesBacktest",
    "distinct_macro_series",
    "run_macro_decomposition",
    "run_walk_forward_backtest",
    "walk_forward_backtest",
]

# Minimum prior same-type observations before a type starts being predicted.
DEFAULT_MIN_TRAIN_PER_TYPE = 3

# Trading-day lookback for pre-event price momentum (PriceMomentumSignal feature).
_MOMENTUM_WINDOW = 20


@dataclass(frozen=True)
class BacktestEvent:
    """One scored event: when it happened, its type, direction, and abnormal return."""

    occurred_at: datetime
    event_type: str
    abnormal_return: float | None
    direction: str | None = None
    # Freshest macro surprise published strictly before this event (or None). Read
    # only by MacroSurpriseSignal; look-ahead-safe by construction of that cutoff.
    macro_surprise: float | None = None
    # Instrument's cumulative return over the window ending strictly before this
    # event (or None). Read only by PriceMomentumSignal; look-ahead-safe.
    pre_event_momentum: float | None = None


@dataclass(frozen=True)
class BacktestResult:
    """Out-of-sample summary for one horizon."""

    model: str  # signal model backtested (e.g. "event_type_history", "llm_direction")
    horizon_days: int
    min_train_per_type: int
    n_events_total: int  # all input events for this horizon (incl. missing outcomes)
    n_dropped_no_outcome: int  # events dropped for a missing abnormal return
    n_events: int  # events with a usable abnormal return
    n_predictions: int  # out-of-sample predictions actually made
    hit_rate: float | None
    mean_strategy_return: float | None  # gross of trading costs
    mean_strategy_return_net: float | None  # net of round-trip commission + slippage
    information_coefficient: float | None
    commission_per_trade: float
    slippage_per_trade: float


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
    commission_per_trade: float = 0.0,
    slippage_per_trade: float = 0.0,
    model: SignalModel | None = None,
) -> BacktestResult:
    """Run the walk-forward backtest of a signal ``model`` over ``events``.

    ``model`` defaults to :class:`~markettrace.impact.signal.EventTypeSignal`
    (the expanding-window history model); pass
    :class:`~markettrace.impact.signal.DirectionSignal` to instead backtest the
    event's own LLM-assigned direction. Every model is driven the same way —
    ``predict`` an event, then ``observe`` its outcome — so a prediction never
    sees its own or any future return regardless of which model is used.

    ``events`` may be in any order; they are sorted by ``occurred_at`` here.
    Events without an abnormal return are dropped (they can be neither predicted
    nor scored) and counted in ``n_dropped_no_outcome`` — a delisted or halted
    stock has no realised return, and hiding that would overstate coverage. Ties
    in ``occurred_at`` keep input order (stable sort), which is conservative: a
    same-day event never trains on its same-day siblings.

    ``commission_per_trade`` and ``slippage_per_trade`` are per-position costs in
    return units (e.g. ``0.001`` = 10 bps). Their sum is a round-trip friction
    subtracted from every position the strategy actually enters
    (``sign(predicted) != 0``) to produce ``mean_strategy_return_net``. Both
    default to ``0.0``, leaving the net figure equal to the gross one.
    """
    if model is None:
        model = EventTypeSignal(min_train=min_train_per_type)

    events = list(events)
    usable = [e for e in events if e.abnormal_return is not None]
    usable.sort(key=lambda e: e.occurred_at)

    predicted: list[float] = []
    realized: list[float] = []

    for event in usable:
        estimate = model.predict(event)
        if estimate is not None:
            predicted.append(estimate)
            realized.append(event.abnormal_return)  # type: ignore[arg-type]
        # Record the outcome only AFTER scoring -> no look-ahead.
        model.observe(event)

    directional = [
        (p, r) for p, r in zip(predicted, realized, strict=True) if _sign(p) != 0 and _sign(r) != 0
    ]
    hit_rate: float | None = None
    if directional:
        hits = sum(1 for p, r in directional if _sign(p) == _sign(r))
        hit_rate = hits / len(directional)

    round_trip_cost = commission_per_trade + slippage_per_trade
    mean_strategy_return: float | None = None
    mean_strategy_return_net: float | None = None
    if predicted:
        gross = [_sign(p) * r for p, r in zip(predicted, realized, strict=True)]
        # A cost is only paid on positions the strategy actually enters (sign != 0).
        net = [
            g - (round_trip_cost if _sign(p) != 0 else 0.0)
            for g, p in zip(gross, predicted, strict=True)
        ]
        mean_strategy_return = sum(gross) / len(gross)
        mean_strategy_return_net = sum(net) / len(net)

    return BacktestResult(
        model=model.name,
        horizon_days=horizon_days,
        min_train_per_type=min_train_per_type,
        n_events_total=len(events),
        n_dropped_no_outcome=len(events) - len(usable),
        n_events=len(usable),
        n_predictions=len(predicted),
        hit_rate=hit_rate,
        mean_strategy_return=mean_strategy_return,
        mean_strategy_return_net=mean_strategy_return_net,
        information_coefficient=_pearson(predicted, realized),
        commission_per_trade=commission_per_trade,
        slippage_per_trade=slippage_per_trade,
    )


def _load_backtest_events(
    session: Session, *, horizon_days: int, macro_series: str | None = None
) -> list[BacktestEvent]:
    """Load scored events for one horizon, each tagged with its macro regime.

    Each event's ``macro_surprise`` is the latest ``surprise_score`` published
    *strictly before* the event's filing time — a cutoff that keeps the macro
    feature look-ahead-safe (an event never sees a surprise the market had not yet
    seen). Events are returned in query order; the backtest sorts them by date.

    ``macro_series`` restricts that regime to a single series (e.g. ``"CPIAUCSL"``)
    instead of the freshest surprise across all series — this is what lets the macro
    signal be *decomposed* per series to see which one, if any, carries the edge.
    """
    rows = session.execute(
        select(
            Document.published_at,
            EventImpact.event_type,
            EventImpact.abnormal_return,
            EventImpact.direction,
            EventImpact.instrument_id,
        )
        .join(Event, Event.id == EventImpact.event_id)
        .join(Document, Document.id == Event.document_id)
        .where(EventImpact.horizon_days == horizon_days)
    ).all()

    # Per-instrument adjusted-close series for look-ahead-safe pre-event momentum.
    prices_by_inst: dict[int, tuple[list, list[float]]] = {}
    for iid, pdate, px in session.execute(
        select(Price.instrument_id, Price.date, Price.adj_close).order_by(
            Price.instrument_id, Price.date
        )
    ).all():
        dates, vals = prices_by_inst.setdefault(iid, ([], []))
        dates.append(pdate)
        vals.append(px)

    def _pre_event_momentum(instrument_id: int, before: datetime) -> float | None:
        series = prices_by_inst.get(instrument_id)
        if series is None:
            return None
        dates, vals = series
        # Prices strictly before the event date only (dates[:idx]).
        idx = bisect.bisect_left(dates, before.date())
        if idx < _MOMENTUM_WINDOW + 1:
            return None
        start = vals[idx - 1 - _MOMENTUM_WINDOW]
        if start == 0:
            return None
        return vals[idx - 1] / start - 1.0

    macro_stmt = select(
        MacroObservation.published_at, MacroObservation.surprise_score
    ).where(MacroObservation.surprise_score.is_not(None))
    if macro_series is not None:
        macro_stmt = macro_stmt.where(MacroObservation.series_id == macro_series)
    macro_rows = session.execute(macro_stmt.order_by(MacroObservation.published_at)).all()
    macro_dates = [r[0] for r in macro_rows]
    macro_values = [r[1] for r in macro_rows]

    def _latest_macro_surprise(before: datetime) -> float | None:
        idx = bisect.bisect_left(macro_dates, before) - 1
        return macro_values[idx] if idx >= 0 else None

    return [
        BacktestEvent(
            occurred_at=r[0],
            event_type=r[1],
            abnormal_return=r[2],
            direction=r[3],
            macro_surprise=_latest_macro_surprise(r[0]),
            pre_event_momentum=_pre_event_momentum(r[4], r[0]),
        )
        for r in rows
    ]


def run_walk_forward_backtest(
    session: Session,
    *,
    horizon_days: int,
    min_train_per_type: int = DEFAULT_MIN_TRAIN_PER_TYPE,
    commission_per_trade: float = 0.0,
    slippage_per_trade: float = 0.0,
    model: SignalModel | None = None,
    macro_series: str | None = None,
) -> BacktestResult:
    """Backtest one horizon from ``event_impacts`` ordered by each event's filing date.

    ``macro_series`` scopes the macro regime feature to a single series (used by the
    macro decomposition); leave it ``None`` for the all-series composite regime.
    """
    events = _load_backtest_events(
        session, horizon_days=horizon_days, macro_series=macro_series
    )
    return walk_forward_backtest(
        events,
        horizon_days=horizon_days,
        min_train_per_type=min_train_per_type,
        commission_per_trade=commission_per_trade,
        slippage_per_trade=slippage_per_trade,
        model=model,
    )


@dataclass(frozen=True)
class MacroSeriesBacktest:
    """One macro series' standalone out-of-sample result at one horizon.

    The composite ``macro_surprise`` model conditions on the *freshest surprise
    across all series*, so a strong IC there could be one series doing the work — or
    just a slow-moving proxy for the calendar. Backtesting each series on its own
    (this row) decomposes that: if the edge concentrates in one economically
    meaningful series it argues for real macro content; if every series looks alike
    it argues for a time/regime proxy.
    """

    series_id: str
    horizon_days: int
    n_predictions: int
    hit_rate: float | None
    mean_strategy_return_net: float | None
    information_coefficient: float | None


def distinct_macro_series(session: Session) -> list[str]:
    """Series ids that have at least one usable surprise, sorted for stable output."""
    rows = session.execute(
        select(MacroObservation.series_id)
        .where(MacroObservation.surprise_score.is_not(None))
        .distinct()
        .order_by(MacroObservation.series_id)
    ).all()
    return [r[0] for r in rows]


def run_macro_decomposition(
    session: Session,
    *,
    horizons: Iterable[int],
    min_train_per_type: int = DEFAULT_MIN_TRAIN_PER_TYPE,
    commission_per_trade: float = 0.0,
    slippage_per_trade: float = 0.0,
) -> list[MacroSeriesBacktest]:
    """Backtest the macro-regime signal on each series independently, per horizon.

    Reuses the same look-ahead-safe walk-forward as the composite macro model, but
    scopes the regime to one series at a time (``macro_series=``) so the composite's
    information coefficient can be attributed series by series.
    """
    horizons = list(horizons)
    results: list[MacroSeriesBacktest] = []
    for series_id in distinct_macro_series(session):
        for horizon in horizons:
            result = run_walk_forward_backtest(
                session,
                horizon_days=horizon,
                min_train_per_type=min_train_per_type,
                commission_per_trade=commission_per_trade,
                slippage_per_trade=slippage_per_trade,
                model=MacroSurpriseSignal(min_train=min_train_per_type),
                macro_series=series_id,
            )
            results.append(
                MacroSeriesBacktest(
                    series_id=series_id,
                    horizon_days=horizon,
                    n_predictions=result.n_predictions,
                    hit_rate=result.hit_rate,
                    mean_strategy_return_net=result.mean_strategy_return_net,
                    information_coefficient=result.information_coefficient,
                )
            )
    return results
