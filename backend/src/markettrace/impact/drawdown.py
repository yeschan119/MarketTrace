"""Trailing-window drawdown — the numeric core of the drop screener (Feature 1).

Feature 1 asks: of the stocks that have *fallen sharply*, which are candidates
to rebound? The first half — "fallen sharply" — is a pure price computation and
lives here, kept ORM-free like :mod:`markettrace.impact.instrument_ranking` so it
unit-tests on synthetic price series and stays reproducible.

The chosen definition (confirmed with the product owner) is **drawdown from the
trailing N-trading-day high**::

    high     = max(adj_close over the last `window` trading days, inclusive)
    current  = latest adj_close
    drawdown = current / high - 1        # <= 0

Adjusted closes are used so splits/dividends don't masquerade as drops
(blueprint §9: unadjusted corporate actions are a classic false signal).

Freshness is a first-class output, not an afterthought: prices in this system
are ingested only around events, so a series can be *stale* (its latest bar is
weeks old). A drawdown computed from stale data is meaningless for "what dropped
*now*", so :class:`DrawdownResult` carries ``as_of``/``latest_date`` and the
caller (the screener endpoint) decides the staleness cutoff rather than this
module silently trusting old bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

__all__ = [
    "DEFAULT_WINDOW",
    "MIN_POINTS",
    "PricePoint",
    "DrawdownResult",
    "compute_drawdown",
    "classify_drop",
]

# Trailing trading-day window whose high defines the reference peak.
DEFAULT_WINDOW = 20

# Minimum bars required in the window to compute a meaningful high. A handful of
# bars (e.g. a single event's price slice) cannot describe a 20-day peak, so we
# return None rather than a misleading drawdown off a 3-bar "high".
MIN_POINTS = 10


@dataclass(frozen=True)
class PricePoint:
    """One daily bar, decoupled from the ORM. ``adj_close`` is split/div adjusted."""

    date: date
    adj_close: float


@dataclass(frozen=True)
class DrawdownResult:
    """Trailing-window drawdown plus the freshness/context needed to judge it."""

    drawdown: float  # current/high - 1, <= 0
    current_price: float
    current_date: date
    high_price: float
    high_date: date
    window_points: int  # bars actually used from the window
    latest_date: date  # newest bar available (== current_date); for staleness


def compute_drawdown(
    prices: list[PricePoint],
    *,
    window: int = DEFAULT_WINDOW,
    min_points: int = MIN_POINTS,
) -> DrawdownResult | None:
    """Return the drawdown of the latest bar from the trailing-``window`` high.

    ``prices`` need not be sorted. The most recent ``window`` bars (by date) are
    considered; the high is the max ``adj_close`` among them and the current is
    the newest bar. Returns ``None`` when fewer than ``min_points`` bars are
    available in the window (too thin to describe a peak) or when the high is
    non-positive (bad data).

    The drawdown is ``<= 0``; ``0.0`` means the latest bar *is* the window high.
    """
    if window < 1 or not prices:
        return None

    ordered = sorted(prices, key=lambda p: p.date)
    recent = ordered[-window:]
    if len(recent) < min_points:
        return None

    current = recent[-1]
    high = max(recent, key=lambda p: p.adj_close)
    if high.adj_close <= 0:
        return None

    return DrawdownResult(
        drawdown=current.adj_close / high.adj_close - 1.0,
        current_price=current.adj_close,
        current_date=current.date,
        high_price=high.adj_close,
        high_date=high.date,
        window_points=len(recent),
        latest_date=current.date,
    )


def classify_drop(lean: str | None, recent_event_count: int) -> str:
    """Label a sharp drop against its validated event context — conservatively.

    The corpus has no validated *bullish* signal, so this never asserts a
    rebound. The three honest buckets:

    * ``persistent_risk`` — recent event(s) *and* a validated-negative (bearish)
      lean: the fall is consistent with this instrument's historical drift, so
      caution likely continues.
    * ``unexplained_drop`` — no recent events in our data explain the fall. It is
      an *observation*, not a buy signal: we simply have no event basis.
    * ``possible_overreaction`` — recent event(s) but the validated lean is not
      negative (neutral/bullish/unranked). A *candidate* for mean-reversion,
      pending backtest validation — explicitly not a buy call.
    """
    if recent_event_count <= 0:
        return "unexplained_drop"
    if lean == "bearish":
        return "persistent_risk"
    return "possible_overreaction"
