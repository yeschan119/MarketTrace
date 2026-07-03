"""Statistical significance of event-type abnormal returns (Phase 4 validation).

The Phase-3 :mod:`markettrace.impact.statistics` layer reports the *mean* and
*dispersion* of abnormal returns per ``(event_type, horizon_days)``. Direction A
(measurement-first) needs the harder question answered: **is that mean
distinguishable from zero, or is it just noise?**

This module runs a one-sample, two-sided t-test (H0: mean abnormal return = 0)
over each bucket and flags whether the sample is even large enough to draw a
conclusion. The two-sided t p-value comes from the SciPy-free
:func:`~markettrace.impact.tstat.two_sided_t_pvalue` (regularised incomplete
beta), shared with the significance-gated signal model.

Caveat — multiple comparisons: many ``(event_type, horizon)`` buckets are tested
at once, so an individual ``significant_5pct`` flag is *exploratory*, not a
confirmed edge. Treat it as "worth a closer look once the sample is adequate",
not proof. ``MIN_SAMPLE`` guards the most common failure mode (n=1 buckets that
look extreme purely by chance).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from sqlalchemy.orm import Session

from markettrace.impact.statistics import EventTypeStat, compute_event_type_statistics
from markettrace.impact.tstat import two_sided_t_pvalue

__all__ = [
    "MIN_SAMPLE",
    "EventTypeSignificance",
    "assess_significance",
    "compute_event_type_significance",
    "two_sided_t_pvalue",  # re-exported from tstat for callers/tests
]

# Below this many observations a bucket is treated as inconclusive regardless of
# the p-value: with n < 5 a single outlier dominates the mean and the t-test is
# not trustworthy. This is the line between "noise" and "worth measuring".
MIN_SAMPLE = 5


@dataclass(frozen=True)
class EventTypeSignificance:
    """Significance verdict for one ``(event_type, horizon_days)`` bucket."""

    event_type: str
    horizon_days: int
    count: int
    mean_abnormal_return: float | None
    std_abnormal_return: float | None
    t_stat: float | None
    p_value: float | None
    # True only when the sample is adequate (``count >= MIN_SAMPLE``) AND the
    # two-sided p-value is below 0.05. Exploratory — see module caveat.
    significant_5pct: bool
    # True when ``count >= MIN_SAMPLE``; below that, any verdict is inconclusive.
    sufficient_sample: bool


def assess_significance(stat: EventTypeStat) -> EventTypeSignificance:
    """Run the one-sample two-sided t-test for a single statistics bucket."""
    n = stat.count
    mean = stat.mean_abnormal_return
    std = stat.std_abnormal_return

    t_stat: float | None = None
    p_value: float | None = None
    if n >= 2 and mean is not None and std is not None and std > 0.0:
        standard_error = std / sqrt(n)
        t_stat = mean / standard_error
        p_value = two_sided_t_pvalue(t_stat, n - 1)

    sufficient = n >= MIN_SAMPLE
    significant = bool(sufficient and p_value is not None and p_value < 0.05)

    return EventTypeSignificance(
        event_type=stat.event_type,
        horizon_days=stat.horizon_days,
        count=n,
        mean_abnormal_return=mean,
        std_abnormal_return=std,
        t_stat=t_stat,
        p_value=p_value,
        significant_5pct=significant,
        sufficient_sample=sufficient,
    )


def compute_event_type_significance(session: Session) -> list[EventTypeSignificance]:
    """Assess significance for every ``(event_type, horizon)`` bucket in the DB."""
    return [assess_significance(stat) for stat in compute_event_type_statistics(session)]
