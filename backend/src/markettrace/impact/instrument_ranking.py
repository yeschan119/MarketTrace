"""Cross-instrument buy-judgment ranking (Phase 5 refinement).

The per-instrument :class:`~markettrace.components.InstrumentSignalCard` view
summarises a single instrument by the *simple mean* of the validated drift of
its events' types. To compare instruments *against each other* — "which name
carries the strongest validated caution right now?" — a simple mean is too
blunt: it treats a stale, low-confidence event the same as a recent,
high-confidence one.

This module refines the aggregate into a **confidence x recency weighted
score** and ranks every instrument by it. The weighting is a deterministic pure
function (blueprint principle 1: numbers are computed by numeric modules, not
the LLM), kept ORM-free like :mod:`markettrace.impact.signal` so it unit-tests
on synthetic inputs and stays reproducible.

Weighting, per validated event ``e`` of an instrument:

    w_e   = confidence_e * 0.5 ** (age_days_e / half_life_days)
    score = sum(w_e * drift_e) / sum(w_e)

where ``drift_e`` is the statistically-significant validated mean abnormal
return for the event's type (the same significance gate the frontend
``assessSignal`` applies), and ``age_days_e`` is measured against an explicit
``as_of`` date so the ranking is deterministic for a given as-of.

Only the *sign* of the validated history matters for the agree/conflict verdict
against the LLM's directional read; the magnitude drives the score. All
historically validated event-type drifts have been negative in this corpus, so
ranking ascending by score surfaces the strongest-caution instruments first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from markettrace.impact.significance import EventTypeSignificance

__all__ = [
    "DEFAULT_HALF_LIFE_DAYS",
    "MIN_VALIDATED_EVENTS",
    "NEUTRAL_BAND",
    "RankedInstrument",
    "RankingEventInput",
    "TopFactor",
    "rank_instruments",
]

# Below this many *validated* events an instrument is not ranked: a single
# validated event is too thin a basis to compare across names.
MIN_VALIDATED_EVENTS = 2

# Half-life (calendar days) of the recency decay. At 180 days an event's weight
# halves every ~6 months, so a year-old filing counts a quarter of a fresh one.
DEFAULT_HALF_LIFE_DAYS = 180.0

# +/- this weighted drift counts as neutral lean (matches the frontend card).
NEUTRAL_BAND = 0.005


@dataclass(frozen=True)
class RankingEventInput:
    """One event's fields needed for ranking, decoupled from the ORM."""

    instrument_id: int
    ticker: str
    name: str
    market: str | None
    event_type: str
    direction: str
    confidence: float
    published_at: datetime
    reviewed_at: datetime | None


@dataclass(frozen=True)
class TopFactor:
    """The event type contributing the most weighted drift for an instrument."""

    event_type: str
    drift: float
    count: int


@dataclass(frozen=True)
class RankedInstrument:
    """An instrument's aggregated, weighted buy-judgment signal."""

    instrument_id: int
    ticker: str
    name: str
    market: str | None
    # Confidence x recency weighted mean of validated drift (market-relative).
    weighted_score: float
    # Unweighted mean of the same validated drifts, for transparency/comparison.
    simple_mean: float
    lean: str  # "bearish" | "bullish" | "neutral"
    validated_count: int
    conflict_count: int
    unreviewed_conflict_count: int
    top_factor: TopFactor | None


def _significant_drift(
    significance_by_type: dict[str, list[EventTypeSignificance]],
    event_type: str,
) -> float | None:
    """The validated mean abnormal return for an event type, or ``None``.

    Mirrors the frontend ``assessSignal`` gate: only ``significant_5pct`` and
    ``sufficient_sample`` rows count; the headline is the lowest-p-value row
    (there is no per-event horizon at the instrument-aggregate level). A zero or
    missing mean is treated as no signal.
    """
    rows = [
        r
        for r in significance_by_type.get(event_type, ())
        if r.significant_5pct and r.sufficient_sample and r.mean_abnormal_return
    ]
    if not rows:
        return None
    headline = min(rows, key=lambda r: r.p_value if r.p_value is not None else 1.0)
    return headline.mean_abnormal_return


def _recency_weight(published_at: datetime, as_of: date, half_life_days: float) -> float:
    """Exponential decay of an event's weight by its age against ``as_of``."""
    age_days = max(0, (as_of - published_at.date()).days)
    return 0.5 ** (age_days / half_life_days)


def _lean(score: float) -> str:
    if score < -NEUTRAL_BAND:
        return "bearish"
    if score > NEUTRAL_BAND:
        return "bullish"
    return "neutral"


def _llm_dir(direction: str) -> str | None:
    key = direction.lower()
    if key == "positive":
        return "up"
    if key == "negative":
        return "down"
    return None


def rank_instruments(
    events: list[RankingEventInput],
    significance: list[EventTypeSignificance],
    as_of: date,
    *,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    min_validated: int = MIN_VALIDATED_EVENTS,
) -> list[RankedInstrument]:
    """Rank instruments by confidence x recency weighted validated drift.

    ``events`` are joined to ``significance`` by event type; only events whose
    type has a statistically validated drift contribute. Instruments with fewer
    than ``min_validated`` such events are dropped. The result is sorted ascending
    by ``weighted_score`` (strongest caution first) with ticker as a stable tie
    break.
    """
    significance_by_type: dict[str, list[EventTypeSignificance]] = {}
    for row in significance:
        significance_by_type.setdefault(row.event_type, []).append(row)

    # Accumulate per instrument.
    @dataclass
    class _Acc:
        ticker: str
        name: str
        market: str | None
        weight_sum: float = 0.0
        weighted_drift_sum: float = 0.0
        drift_sum: float = 0.0
        validated_count: int = 0
        conflict_count: int = 0
        unreviewed_conflict_count: int = 0

    accs: dict[int, _Acc] = {}
    # Per (instrument, event_type) weighted drift, for the top factor.
    factor_weight: dict[tuple[int, str], float] = {}
    factor_drift_sum: dict[tuple[int, str], float] = {}
    factor_count: dict[tuple[int, str], int] = {}

    for e in events:
        drift = _significant_drift(significance_by_type, e.event_type)
        if drift is None:
            continue

        acc = accs.get(e.instrument_id)
        if acc is None:
            acc = _Acc(ticker=e.ticker, name=e.name, market=e.market)
            accs[e.instrument_id] = acc

        weight = e.confidence * _recency_weight(e.published_at, as_of, half_life_days)
        acc.weight_sum += weight
        acc.weighted_drift_sum += weight * drift
        acc.drift_sum += drift
        acc.validated_count += 1

        ld = _llm_dir(e.direction)
        hd = "up" if drift > 0 else "down"
        if ld is not None and ld != hd:
            acc.conflict_count += 1
            if e.reviewed_at is None:
                acc.unreviewed_conflict_count += 1

        key = (e.instrument_id, e.event_type)
        factor_weight[key] = factor_weight.get(key, 0.0) + weight
        factor_drift_sum[key] = factor_drift_sum.get(key, 0.0) + weight * drift
        factor_count[key] = factor_count.get(key, 0) + 1

    ranked: list[RankedInstrument] = []
    for instrument_id, acc in accs.items():
        if acc.validated_count < min_validated or acc.weight_sum <= 0.0:
            continue
        weighted_score = acc.weighted_drift_sum / acc.weight_sum
        simple_mean = acc.drift_sum / acc.validated_count

        # Top factor: the event type with the largest absolute weighted
        # contribution for this instrument.
        top_factor: TopFactor | None = None
        best_abs = -1.0
        for (iid, etype), w in factor_weight.items():
            if iid != instrument_id or w <= 0.0:
                continue
            type_drift = factor_drift_sum[(iid, etype)] / w
            if abs(type_drift) > best_abs:
                best_abs = abs(type_drift)
                top_factor = TopFactor(
                    event_type=etype,
                    drift=type_drift,
                    count=factor_count[(iid, etype)],
                )

        ranked.append(
            RankedInstrument(
                instrument_id=instrument_id,
                ticker=acc.ticker,
                name=acc.name,
                market=acc.market,
                weighted_score=weighted_score,
                simple_mean=simple_mean,
                lean=_lean(weighted_score),
                validated_count=acc.validated_count,
                conflict_count=acc.conflict_count,
                unreviewed_conflict_count=acc.unreviewed_conflict_count,
                top_factor=top_factor,
            )
        )

    ranked.sort(key=lambda r: (r.weighted_score, r.ticker))
    return ranked
