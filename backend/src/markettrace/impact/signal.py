"""Signal models over event history (Phase 4: model separation).

The blueprint (§7-4) calls for the predictive layer to be split into independent,
swappable *models* — fundamental, event, macro, price, flow — each estimating an
expected reaction that downstream code combines and backtests uniformly. This
module holds the first two and the common interface they share.

A :class:`SignalModel` turns an event into an *expected abnormal return* whose
sign is the position the strategy would take. The walk-forward backtest drives
any model the same way: :meth:`~SignalModel.predict` an event, then
:meth:`~SignalModel.observe` its realised outcome — strictly in that order, so a
prediction never sees its own or any future return.

The models that ship here:

* :class:`EventTypeSignal` — learns each event type's mean abnormal return from
  history (an expanding window). Needs training; look-ahead-safe by construction.
* :class:`SignificantEventTypeSignal` — the same expanding-window mean, but only
  takes a position on types whose training-window edge is statistically
  distinguishable from zero (one-sample t-test, p<α). Operationalises Direction A:
  trade only the validated signals, stay flat on noise.
* :class:`MacroSurpriseSignal` — learns the mean abnormal return conditioned on the
  *macro regime* (the sign of the freshest macro surprise known at filing time),
  asking whether the macro backdrop — not the event's type — carries information.
* :class:`CombinedSignal` — equal-weight combination of several expected-return
  models, so their signals can be backtested together rather than in isolation.
* :class:`DirectionSignal` — trades the event's own LLM-assigned ``direction``
  (호재/악재), which is known at the moment the disclosure lands (t=0). Needs no
  training and answers the project's core question directly: does the model's
  stated direction actually predict the sign of the abnormal return?
"""

from __future__ import annotations

from math import sqrt
from typing import Protocol, runtime_checkable

from markettrace.impact.tstat import two_sided_t_pvalue

__all__ = [
    "SIGNAL_MODEL_NAMES",
    "CombinedSignal",
    "DirectionSignal",
    "EventTypeSignal",
    "MacroSurpriseSignal",
    "SignalInput",
    "SignalModel",
    "SignificantEventTypeSignal",
    "make_signal_model",
]

# Sample floor below which a t-test is not trustworthy: with n < 5 a single
# outlier dominates the mean. Mirrors significance.MIN_SAMPLE, duplicated here to
# keep this module free of the ORM import chain that significance.py pulls in.
_SIGNIFICANCE_MIN_SAMPLE = 5

# Event direction -> position sign. Mirrors event_impacts.direction_sign but is
# duplicated here on purpose to keep this module free of the ORM/polars import
# chain that event_impacts pulls in.
_DIRECTION_POSITION: dict[str, int] = {"positive": 1, "negative": -1, "neutral": 0}


def _sign_int(x: float) -> int:
    """Sign of ``x`` as -1 / 0 / +1 (used to bucket the macro-surprise regime)."""
    if x > 0.0:
        return 1
    if x < 0.0:
        return -1
    return 0


@runtime_checkable
class SignalInput(Protocol):
    """The event fields a signal model may read. ``BacktestEvent`` satisfies it."""

    event_type: str
    direction: str | None
    abnormal_return: float | None
    # Freshest macro surprise known at the event's filing time (or None). Read by
    # MacroSurpriseSignal; other models ignore it.
    macro_surprise: float | None


class SignalModel(Protocol):
    """A predictive model over events, driven predict-then-observe by the backtest."""

    name: str

    def observe(self, event: SignalInput) -> None:
        """Record ``event``'s realised outcome for future predictions."""
        ...

    def predict(self, event: SignalInput) -> float | None:
        """Expected abnormal return for ``event``, or ``None`` to make no call."""
        ...


class EventTypeSignal:
    """Expanding-window mean of each event type's realised abnormal returns.

    The estimate for a type is the arithmetic mean of every abnormal return
    :meth:`observe`\\ d for that type so far. :meth:`predict` returns ``None``
    until a type has at least ``min_train`` prior observations, mirroring the
    backtest's minimum-training gate.
    """

    name = "event_type_history"

    def __init__(self, *, min_train: int) -> None:
        self.min_train = min_train
        self._history: dict[str, list[float]] = {}

    def observe(self, event: SignalInput) -> None:
        """Record one realised abnormal return, keyed by event type."""
        if event.abnormal_return is None:
            return
        self._history.setdefault(event.event_type, []).append(event.abnormal_return)

    def predict(self, event: SignalInput) -> float | None:
        """Mean of ``event.event_type``'s prior returns, or ``None`` if undertrained.

        Returns ``None`` when the type has fewer than ``min_train`` prior
        observations (including an entirely unseen type); otherwise the mean of
        its observed abnormal returns.
        """
        prior = self._history.get(event.event_type)
        if prior is None or len(prior) < self.min_train:
            return None
        return sum(prior) / len(prior)


class SignificantEventTypeSignal:
    """Expanding-window mean, but only traded when the type's edge is significant.

    Identical bookkeeping to :class:`EventTypeSignal` — an expanding history of
    each type's realised abnormal returns — but :meth:`predict` first runs a
    one-sample two-sided t-test (H0: mean = 0) over that type's *prior* returns and
    returns ``None`` unless the sample is adequate AND the p-value is below
    ``alpha``. This is Direction A made tradeable: only event types the data has
    statistically validated get a position; governance-noise types whose mean is
    indistinguishable from zero stay flat.

    The test uses only prior-observed returns (the same ones the mean averages), so
    it is look-ahead-safe: a type must build a significant track record before it is
    ever traded. The sample floor is ``max(min_train, _SIGNIFICANCE_MIN_SAMPLE)``.
    """

    name = "significant_event_type"

    def __init__(self, *, min_train: int, alpha: float = 0.05) -> None:
        self.min_train = max(min_train, _SIGNIFICANCE_MIN_SAMPLE)
        self.alpha = alpha
        self._history: dict[str, list[float]] = {}

    def observe(self, event: SignalInput) -> None:
        """Record one realised abnormal return, keyed by event type."""
        if event.abnormal_return is None:
            return
        self._history.setdefault(event.event_type, []).append(event.abnormal_return)

    def predict(self, event: SignalInput) -> float | None:
        """Mean of the type's prior returns, but only if that mean is significant.

        Returns ``None`` when the type has fewer than ``min_train`` prior
        observations, when the prior returns have zero spread (degenerate t-test),
        or when the two-sided p-value is at or above ``alpha``. Otherwise returns
        the mean of the type's observed abnormal returns (its position estimate).
        """
        prior = self._history.get(event.event_type)
        if prior is None or len(prior) < self.min_train:
            return None
        n = len(prior)
        mean = sum(prior) / n
        variance = sum((x - mean) ** 2 for x in prior) / (n - 1)
        if variance <= 0.0:
            return None
        std_error = sqrt(variance) / sqrt(n)
        p_value = two_sided_t_pvalue(mean / std_error, n - 1)
        if p_value is None or p_value >= self.alpha:
            return None
        return mean


class MacroSurpriseSignal:
    """Expanding-window mean abnormal return conditioned on the macro regime.

    Keys history on the *sign* of the freshest macro surprise known at the event's
    filing time (``sign(macro_surprise)`` ∈ {-1, 0, +1}) and predicts that bucket's
    historical mean. Unlike the event-type model this asks whether the prevailing
    macro-surprise regime — not the event's own type — carries return information.

    It assumes no economic direction: the regime→return relationship is *learned*
    from history (measurement-first), so a positive surprise is not presumed good or
    bad. ``macro_surprise`` is a single scalar (the latest ``surprise_score`` across
    all macro series published before the event); collapsing several series with
    different sign conventions into one number is a known v1 limitation — a
    per-series or multivariate regime model is future work. Look-ahead-safe: only
    prior-observed (regime, return) pairs enter the estimate.
    """

    name = "macro_surprise"

    def __init__(self, *, min_train: int) -> None:
        self.min_train = min_train
        self._history: dict[int, list[float]] = {}

    def observe(self, event: SignalInput) -> None:
        """Record one realised return, keyed by the sign of the macro surprise."""
        if event.abnormal_return is None or event.macro_surprise is None:
            return
        self._history.setdefault(_sign_int(event.macro_surprise), []).append(
            event.abnormal_return
        )

    def predict(self, event: SignalInput) -> float | None:
        """Mean return for the event's macro regime, or ``None`` if unknown/undertrained."""
        if event.macro_surprise is None:
            return None
        prior = self._history.get(_sign_int(event.macro_surprise))
        if prior is None or len(prior) < self.min_train:
            return None
        return sum(prior) / len(prior)


class CombinedSignal:
    """Equal-weight combination of several expected-return signal models.

    Forwards :meth:`observe` to every constituent so they each learn, and predicts
    the mean of the constituents' non-``None`` estimates — all in abnormal-return
    units, so the average is meaningful. Returns ``None`` only when *every*
    constituent abstains; the backtest trades the sign of the combined estimate.

    Constituents must output expected *returns* (e.g. :class:`EventTypeSignal`,
    :class:`MacroSurpriseSignal`), not position signs — averaging a return with a
    ±1 direction would mix units.
    """

    name = "combined"

    def __init__(self, models: list[SignalModel]) -> None:
        self._models = models

    def observe(self, event: SignalInput) -> None:
        """Forward the outcome to every constituent model."""
        for model in self._models:
            model.observe(event)

    def predict(self, event: SignalInput) -> float | None:
        """Mean of the constituents' non-``None`` estimates, or ``None`` if all abstain."""
        estimates = [
            estimate
            for model in self._models
            if (estimate := model.predict(event)) is not None
        ]
        if not estimates:
            return None
        return sum(estimates) / len(estimates)


class DirectionSignal:
    """Trade the event's own LLM-assigned direction, known at t=0 (no training).

    ``positive`` → long (+1), ``negative`` → short (-1), ``neutral`` → flat (0).
    An event with no direction gets ``None`` (no call). The prediction is a bare
    position sign; the backtest uses only its sign, so the unit magnitude is
    immaterial. :meth:`observe` is a no-op — this model carries no state.
    """

    name = "llm_direction"

    def observe(self, event: SignalInput) -> None:
        """No-op: the direction signal needs no history."""

    def predict(self, event: SignalInput) -> float | None:
        if event.direction is None:
            return None
        return float(_DIRECTION_POSITION.get(event.direction, 0))


def make_signal_model(name: str, *, min_train: int) -> SignalModel:
    """Build a signal model by name (``min_train`` used only where a model trains)."""
    if name == EventTypeSignal.name:
        return EventTypeSignal(min_train=min_train)
    if name == SignificantEventTypeSignal.name:
        return SignificantEventTypeSignal(min_train=min_train)
    if name == MacroSurpriseSignal.name:
        return MacroSurpriseSignal(min_train=min_train)
    if name == CombinedSignal.name:
        # Combine the two expected-return models (matching units); the LLM-direction
        # and significance-gated models are kept separate/standalone by design.
        return CombinedSignal(
            [EventTypeSignal(min_train=min_train), MacroSurpriseSignal(min_train=min_train)]
        )
    if name == DirectionSignal.name:
        return DirectionSignal()
    raise ValueError(f"unknown signal model: {name!r}")


# Model names selectable at the API boundary, in report order.
SIGNAL_MODEL_NAMES: tuple[str, ...] = (
    EventTypeSignal.name,
    SignificantEventTypeSignal.name,
    MacroSurpriseSignal.name,
    CombinedSignal.name,
    DirectionSignal.name,
)
