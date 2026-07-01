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

Two concrete models ship here:

* :class:`EventTypeSignal` — learns each event type's mean abnormal return from
  history (an expanding window). Needs training; look-ahead-safe by construction.
* :class:`DirectionSignal` — trades the event's own LLM-assigned ``direction``
  (호재/악재), which is known at the moment the disclosure lands (t=0). Needs no
  training and answers the project's core question directly: does the model's
  stated direction actually predict the sign of the abnormal return?
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = [
    "SIGNAL_MODEL_NAMES",
    "DirectionSignal",
    "EventTypeSignal",
    "SignalInput",
    "SignalModel",
    "make_signal_model",
]

# Event direction -> position sign. Mirrors event_impacts.direction_sign but is
# duplicated here on purpose to keep this module free of the ORM/polars import
# chain that event_impacts pulls in.
_DIRECTION_POSITION: dict[str, int] = {"positive": 1, "negative": -1, "neutral": 0}


@runtime_checkable
class SignalInput(Protocol):
    """The event fields a signal model may read. ``BacktestEvent`` satisfies it."""

    event_type: str
    direction: str | None
    abnormal_return: float | None


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
    if name == DirectionSignal.name:
        return DirectionSignal()
    raise ValueError(f"unknown signal model: {name!r}")


# Model names selectable at the API boundary, in report order.
SIGNAL_MODEL_NAMES: tuple[str, ...] = (EventTypeSignal.name, DirectionSignal.name)
