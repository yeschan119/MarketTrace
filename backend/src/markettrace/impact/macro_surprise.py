"""Macroeconomic surprise computation (blueprint §7-3, §3).

The *surprise* of a release is how far the actual value landed from what was
expected, standardized so it is comparable across series:

    surprise = (released - expected) / scale

``expected`` comes from a real consensus forecast when one is supplied;
otherwise it falls back to a deterministic *baseline* (a random-walk forecast =
the prior reading), and ``scale`` is the dispersion of the series' historical
period-over-period changes. Everything here is a pure function over scalars and
ordered history, so results are reproducible (§2) and never peek at future data
(§9): each observation's expectation and scale use only values released before
it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import sqrt

from markettrace.db.models import MacroObservation
from markettrace.providers.base import MacroPoint

__all__ = [
    "SurpriseResult",
    "baseline_expectation",
    "change_scale",
    "compute_surprise",
    "build_macro_observations",
]


@dataclass(frozen=True)
class SurpriseResult:
    """The surprise of one release and the expectation it was measured against."""

    series_id: str
    released: float
    expected: float | None
    expected_source: str | None
    surprise_score: float | None


def baseline_expectation(history: Sequence[float]) -> float | None:
    """Random-walk forecast: the most recent prior reading, or ``None`` if none.

    This is the naive expectation used when no consensus forecast is available;
    a release is then "surprising" insofar as it differs from the prior reading.
    """
    return history[-1] if history else None


def change_scale(history: Sequence[float]) -> float | None:
    """Sample std (ddof=1) of consecutive changes in *history*.

    Returns ``None`` when there are fewer than two changes (need >= 3 points) or
    the changes have no dispersion, so the caller leaves surprise ``None`` rather
    than dividing by zero.
    """
    if len(history) < 3:
        return None
    diffs = [history[i + 1] - history[i] for i in range(len(history) - 1)]
    n = len(diffs)
    mean = sum(diffs) / n
    variance = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    scale = sqrt(variance)
    return scale if scale > 0 else None


def compute_surprise(
    released: float | None, expected: float | None, scale: float | None
) -> float | None:
    """Standardized surprise ``(released - expected) / scale``.

    Any missing component (``None`` expected/scale, or a zero scale) yields
    ``None`` so the figure degrades gracefully instead of misreporting.
    """
    if released is None or expected is None or scale is None or scale == 0:
        return None
    return (released - expected) / scale


def build_macro_observations(
    points: Sequence[MacroPoint],
    *,
    now: datetime,
    expected_lookup: dict | None = None,
    prior_history: Sequence[float] | None = None,
) -> list[MacroObservation]:
    """Create one :class:`MacroObservation` per point with surprise filled in.

    *points* must be ordered ascending by ``reference_date`` (the FRED provider
    guarantees this). For each point the expectation is the consensus value from
    *expected_lookup* (keyed by ``reference_date``) when present — marked
    ``expected_source="consensus"`` — otherwise the random-walk baseline over the
    prior releases (``"baseline"``). The scale uses only prior releases, so no
    observation depends on a value released after it. Rows are returned (not
    added to a session) so the caller controls persistence.

    *prior_history* seeds the baseline/scale history with released values from
    periods *before* the first point — released ascending. An incremental fetch
    (only the newest releases) passes the earlier values stored in the DB here so
    each new observation's expectation and scale match a full-history compute,
    without re-downloading decades of data.
    """
    expected_lookup = expected_lookup or {}
    rows: list[MacroObservation] = []
    # Released values strictly before the current point, seeded with any history
    # the caller already holds (e.g. prior DB rows for an incremental fetch).
    history: list[float] = list(prior_history or [])

    for point in points:
        consensus = expected_lookup.get(point.reference_date)
        if consensus is not None:
            expected: float | None = float(consensus)
            expected_source: str | None = "consensus"
        else:
            expected = baseline_expectation(history)
            expected_source = "baseline" if expected is not None else None

        scale = change_scale(history)
        surprise = compute_surprise(point.released_value, expected, scale)

        ref = point.reference_date
        rows.append(
            MacroObservation(
                series_id=point.series_id,
                reference_date=ref,
                released_value=point.released_value,
                previous_value=point.previous_value,
                expected_value=expected,
                expected_source=expected_source,
                surprise_score=surprise,
                occurred_at=datetime(ref.year, ref.month, ref.day, tzinfo=UTC),
                published_at=point.released_at,
                first_seen_at=now,
                revision=0,
                source="fred",
            )
        )
        history.append(point.released_value)

    return rows
