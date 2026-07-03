"""Confidence calibration of the LLM's directional call (Phase 4 validation).

The blueprint (§8) sets a sharper bar than accuracy: a prediction stamped
``confidence = 0.7`` should be right about 70% of the time over the long run. This
module measures whether the extractor's stated ``confidence`` behaves like that — a
*reliability curve* — for its directional call.

A single directional prediction is the event's LLM ``direction`` (positive → long,
negative → short; neutral makes no call) carrying the event's ``confidence`` as its
stated probability of being right. It is *correct* when the sign of the direction
matches the sign of the realised abnormal return at the horizon. Predictions are
binned by confidence; per bin we compare the mean stated confidence to the observed
hit rate (accuracy). Two scalars summarise the gap:

* ``expected_calibration_error`` (ECE) — sample-weighted mean ``|confidence − hit|``
  across non-empty bins. 0 = perfectly calibrated.
* ``brier_score`` — mean ``(confidence − correct)²`` over predictions (lower better).

Caveat — the extractor's ``confidence`` is a *classification* confidence, not trained
as a directional-hit probability, so miscalibration here is expected; quantifying it
is exactly the point, because a confidence-weighted combination of signals is only
trustworthy once we know what a given confidence is worth. Only directional
predictions with a realised, non-zero outcome are scored; neutral calls and
missing/zero returns are excluded and counted, so shrinking coverage stays visible
rather than silently inflating the hit rate.

Pure function over records (trivially testable); a thin session helper pulls
``(confidence, direction, abnormal_return)`` from ``event_impacts`` joined to each
event's ``confidence``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import Event, EventImpact

__all__ = [
    "DEFAULT_CALIBRATION_BINS",
    "CalibrationBin",
    "CalibrationReport",
    "calibrate",
    "compute_confidence_calibration",
]

# Reliability-diagram resolution: 10 equal-width confidence bins over [0, 1].
DEFAULT_CALIBRATION_BINS = 10

# Event direction -> position sign. Mirrors signal._DIRECTION_POSITION; a neutral
# (or unknown) direction is not a directional call and is excluded from scoring.
_DIRECTION_SIGN: dict[str, int] = {"positive": 1, "negative": -1, "neutral": 0}


def _sign(x: float) -> int:
    if x > 0.0:
        return 1
    if x < 0.0:
        return -1
    return 0


def _clamp01(x: float) -> float:
    """Confidence should be in [0, 1]; clamp defensively so binning never overflows."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


@dataclass(frozen=True)
class CalibrationBin:
    """One confidence bucket of the reliability curve.

    ``gap`` is ``mean_confidence − hit_rate``: positive means the model was
    *overconfident* in this band (claimed more certainty than it delivered),
    negative means *underconfident*. All three stats are ``None`` for an empty bin.
    """

    lower: float
    upper: float
    count: int
    mean_confidence: float | None
    hit_rate: float | None
    gap: float | None


@dataclass(frozen=True)
class CalibrationReport:
    """Directional-call calibration for one horizon.

    Coverage is reported honestly: ``n_events_total`` is every event at the horizon,
    ``n_dropped_neutral`` the non-directional calls, ``n_dropped_no_outcome`` the
    directional calls whose realised return is missing or exactly zero, and
    ``n_predictions`` the directional predictions actually scored (= sum of bin
    counts).
    """

    horizon_days: int
    n_bins: int
    n_events_total: int
    n_dropped_neutral: int
    n_dropped_no_outcome: int
    n_predictions: int
    mean_confidence: float | None
    hit_rate: float | None
    expected_calibration_error: float | None
    brier_score: float | None
    bins: list[CalibrationBin]


def calibrate(
    predictions: Iterable[tuple[float, str | None, float | None]],
    *,
    horizon_days: int,
    n_bins: int = DEFAULT_CALIBRATION_BINS,
) -> CalibrationReport:
    """Reliability of the directional call at one horizon.

    ``predictions`` are ``(confidence, direction, abnormal_return)`` triples. A
    triple is *scored* only when the direction is a real call (positive/negative),
    the abnormal return is present, and its sign is non-zero; every other triple is
    excluded and reported in the ``n_dropped_*`` counters. Confidence is clamped to
    ``[0, 1]`` before binning. Raises ``ValueError`` if ``n_bins < 1``.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")

    triples = list(predictions)
    n_total = len(triples)

    scored: list[tuple[float, bool]] = []  # (confidence, correct)
    n_neutral = 0
    n_no_outcome = 0
    for confidence, direction, abnormal_return in triples:
        sign_dir = _DIRECTION_SIGN.get(direction or "", 0)
        if sign_dir == 0:
            n_neutral += 1
            continue
        if abnormal_return is None or _sign(abnormal_return) == 0:
            n_no_outcome += 1
            continue
        scored.append((_clamp01(confidence), sign_dir == _sign(abnormal_return)))

    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for conf, correct in scored:
        # conf == 1.0 would index n_bins; clamp it into the final bin.
        idx = min(int(conf * n_bins), n_bins - 1)
        buckets[idx].append((conf, correct))

    bins: list[CalibrationBin] = []
    ece_weighted = 0.0
    for i, bucket in enumerate(buckets):
        count = len(bucket)
        if count:
            mean_conf = sum(c for c, _ in bucket) / count
            hit = sum(1 for _, ok in bucket if ok) / count
            gap = mean_conf - hit
            ece_weighted += count * abs(gap)
        else:
            mean_conf = hit = gap = None
        bins.append(
            CalibrationBin(
                lower=i / n_bins,
                upper=(i + 1) / n_bins,
                count=count,
                mean_confidence=mean_conf,
                hit_rate=hit,
                gap=gap,
            )
        )

    n_pred = len(scored)
    mean_confidence: float | None = None
    hit_rate: float | None = None
    ece: float | None = None
    brier: float | None = None
    if n_pred:
        mean_confidence = sum(c for c, _ in scored) / n_pred
        hit_rate = sum(1 for _, ok in scored if ok) / n_pred
        ece = ece_weighted / n_pred
        brier = sum((c - (1.0 if ok else 0.0)) ** 2 for c, ok in scored) / n_pred

    return CalibrationReport(
        horizon_days=horizon_days,
        n_bins=n_bins,
        n_events_total=n_total,
        n_dropped_neutral=n_neutral,
        n_dropped_no_outcome=n_no_outcome,
        n_predictions=n_pred,
        mean_confidence=mean_confidence,
        hit_rate=hit_rate,
        expected_calibration_error=ece,
        brier_score=brier,
        bins=bins,
    )


def compute_confidence_calibration(
    session: Session,
    *,
    horizons: Iterable[int],
    n_bins: int = DEFAULT_CALIBRATION_BINS,
) -> list[CalibrationReport]:
    """Calibrate the directional call for each horizon from ``event_impacts``.

    Joins each impact row to its event's ``confidence`` (the LLM's stated certainty)
    and scores the event's ``direction`` against the realised ``abnormal_return``.
    Returns one report per horizon, in the order given.
    """
    reports: list[CalibrationReport] = []
    for horizon in horizons:
        rows = session.execute(
            select(
                Event.confidence,
                EventImpact.direction,
                EventImpact.abnormal_return,
            )
            .select_from(EventImpact)
            .join(Event, Event.id == EventImpact.event_id)
            .where(EventImpact.horizon_days == horizon)
        ).all()
        reports.append(
            calibrate(
                ((r[0], r[1], r[2]) for r in rows),
                horizon_days=horizon,
                n_bins=n_bins,
            )
        )
    return reports
