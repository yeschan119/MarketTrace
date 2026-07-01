"""Tests for the signal models: EventTypeSignal (history) + DirectionSignal (t=0)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from markettrace.impact.signal import (
    SIGNAL_MODEL_NAMES,
    DirectionSignal,
    EventTypeSignal,
    make_signal_model,
)


@dataclass
class _Ev:
    """Minimal SignalInput stand-in (structurally matches BacktestEvent)."""

    event_type: str = "x"
    abnormal_return: float | None = None
    direction: str | None = None


# ---------------------------------------------------------------------------
# EventTypeSignal — expanding-window mean per type
# ---------------------------------------------------------------------------


def test_unknown_type_predicts_none() -> None:
    sig = EventTypeSignal(min_train=1)
    assert sig.predict(_Ev(event_type="earnings")) is None


def test_undertrained_type_predicts_none() -> None:
    sig = EventTypeSignal(min_train=3)
    sig.observe(_Ev("earnings", 0.02))
    sig.observe(_Ev("earnings", 0.04))
    assert sig.predict(_Ev(event_type="earnings")) is None


def test_predict_returns_mean_once_trained() -> None:
    sig = EventTypeSignal(min_train=3)
    for ar in (0.02, 0.04, 0.06):
        sig.observe(_Ev("earnings", ar))
    assert sig.predict(_Ev(event_type="earnings")) == 0.04


def test_min_train_boundary_is_inclusive() -> None:
    sig = EventTypeSignal(min_train=2)
    sig.observe(_Ev("x", 0.01))
    sig.observe(_Ev("x", 0.03))
    assert sig.predict(_Ev(event_type="x")) == 0.02


def test_types_are_independent() -> None:
    sig = EventTypeSignal(min_train=2)
    sig.observe(_Ev("a", 0.10))
    sig.observe(_Ev("a", 0.20))
    sig.observe(_Ev("b", -0.05))
    sig.observe(_Ev("b", -0.15))
    assert sig.predict(_Ev(event_type="a")) == pytest.approx(0.15)
    assert sig.predict(_Ev(event_type="b")) == pytest.approx(-0.10)


def test_observe_ignores_missing_outcome() -> None:
    sig = EventTypeSignal(min_train=1)
    sig.observe(_Ev("x", None))  # delisted/halted -> no realised return to learn from
    assert sig.predict(_Ev(event_type="x")) is None
    sig.observe(_Ev("x", 0.02))
    assert sig.predict(_Ev(event_type="x")) == 0.02


# ---------------------------------------------------------------------------
# DirectionSignal — trade the event's own LLM direction, no training
# ---------------------------------------------------------------------------


def test_direction_maps_to_position_sign() -> None:
    sig = DirectionSignal()
    assert sig.predict(_Ev(direction="positive")) == 1.0
    assert sig.predict(_Ev(direction="negative")) == -1.0
    assert sig.predict(_Ev(direction="neutral")) == 0.0


def test_direction_none_makes_no_call() -> None:
    assert DirectionSignal().predict(_Ev(direction=None)) is None


def test_direction_unknown_string_is_flat() -> None:
    assert DirectionSignal().predict(_Ev(direction="sideways")) == 0.0


def test_direction_needs_no_training() -> None:
    # Prediction is available on the very first event, before any observe().
    sig = DirectionSignal()
    assert sig.predict(_Ev(direction="positive")) == 1.0
    sig.observe(_Ev(direction="positive", abnormal_return=0.05))  # no-op, must not raise
    assert sig.predict(_Ev(direction="positive")) == 1.0


# ---------------------------------------------------------------------------
# make_signal_model factory
# ---------------------------------------------------------------------------


def test_factory_builds_named_models() -> None:
    assert isinstance(make_signal_model("event_type_history", min_train=3), EventTypeSignal)
    assert isinstance(make_signal_model("llm_direction", min_train=3), DirectionSignal)


def test_factory_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="unknown signal model"):
        make_signal_model("nope", min_train=3)


def test_registered_model_names() -> None:
    assert SIGNAL_MODEL_NAMES == ("event_type_history", "llm_direction")
