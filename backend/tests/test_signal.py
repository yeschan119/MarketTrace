"""Tests for the signal models: EventTypeSignal (history) + DirectionSignal (t=0)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from markettrace.impact.signal import (
    SIGNAL_MODEL_NAMES,
    CombinedSignal,
    DirectionSignal,
    EventTypeSignal,
    MacroSurpriseSignal,
    SignificantEventTypeSignal,
    make_signal_model,
)


@dataclass
class _Ev:
    """Minimal SignalInput stand-in (structurally matches BacktestEvent)."""

    event_type: str = "x"
    abnormal_return: float | None = None
    direction: str | None = None
    macro_surprise: float | None = None


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
# SignificantEventTypeSignal — expanding mean, gated on a significant t-test
# ---------------------------------------------------------------------------


def _train(sig: SignificantEventTypeSignal, event_type: str, returns: list[float]) -> None:
    for r in returns:
        sig.observe(_Ev(event_type, r))


def test_significant_enforces_min_sample_floor() -> None:
    # Even with min_train=2, the significance floor (5) governs: 4 obs -> no call.
    sig = SignificantEventTypeSignal(min_train=2)
    assert sig.min_train == 5
    _train(sig, "x", [-0.05, -0.05, -0.05, -0.05])
    assert sig.predict(_Ev(event_type="x")) is None


def test_significant_trades_a_consistent_edge() -> None:
    # A tight, clearly-nonzero negative edge over an adequate sample -> significant,
    # so the model takes the position (returns the mean, which is negative).
    sig = SignificantEventTypeSignal(min_train=5)
    _train(sig, "insider", [-0.06, -0.05, -0.07, -0.06, -0.065, -0.055])
    est = sig.predict(_Ev(event_type="insider"))
    assert est is not None
    assert est < 0.0


def test_significant_stays_flat_on_noise() -> None:
    # A mean near zero with wide spread is indistinguishable from zero -> no call,
    # even though the sample is adequate. This is the governance-noise filter.
    sig = SignificantEventTypeSignal(min_train=5)
    _train(sig, "governance", [0.10, -0.11, 0.09, -0.10, 0.08, -0.06])
    assert sig.predict(_Ev(event_type="governance")) is None


def test_significant_zero_variance_makes_no_call() -> None:
    # Degenerate: identical returns -> zero spread -> t-test undefined -> no call.
    sig = SignificantEventTypeSignal(min_train=5)
    _train(sig, "x", [0.02, 0.02, 0.02, 0.02, 0.02])
    assert sig.predict(_Ev(event_type="x")) is None


def test_significant_is_look_ahead_safe() -> None:
    # predict() sees only what has been observed so far; the current event's own
    # (as-yet-unobserved) return never enters the estimate.
    sig = SignificantEventTypeSignal(min_train=5)
    _train(sig, "x", [-0.06, -0.05, -0.07, -0.06])  # only 4 so far
    assert sig.predict(_Ev(event_type="x")) is None  # under the floor of 5
    sig.observe(_Ev("x", -0.065))  # now 5
    assert sig.predict(_Ev(event_type="x")) is not None


# ---------------------------------------------------------------------------
# MacroSurpriseSignal — expanding mean conditioned on the macro regime (sign)
# ---------------------------------------------------------------------------


def test_macro_none_surprise_makes_no_call() -> None:
    sig = MacroSurpriseSignal(min_train=1)
    sig.observe(_Ev(abnormal_return=0.02, macro_surprise=0.5))
    assert sig.predict(_Ev(macro_surprise=None)) is None


def test_macro_learns_per_regime_sign() -> None:
    sig = MacroSurpriseSignal(min_train=2)
    # Positive-surprise regime tends up; negative-surprise regime tends down.
    sig.observe(_Ev(abnormal_return=0.03, macro_surprise=0.8))
    sig.observe(_Ev(abnormal_return=0.05, macro_surprise=0.2))
    sig.observe(_Ev(abnormal_return=-0.04, macro_surprise=-0.6))
    sig.observe(_Ev(abnormal_return=-0.02, macro_surprise=-0.1))
    assert sig.predict(_Ev(macro_surprise=1.5)) == pytest.approx(0.04)
    assert sig.predict(_Ev(macro_surprise=-0.9)) == pytest.approx(-0.03)


def test_macro_undertrained_regime_predicts_none() -> None:
    sig = MacroSurpriseSignal(min_train=3)
    sig.observe(_Ev(abnormal_return=0.03, macro_surprise=0.8))
    sig.observe(_Ev(abnormal_return=0.05, macro_surprise=0.2))
    assert sig.predict(_Ev(macro_surprise=0.4)) is None  # only 2 in the + bucket


def test_macro_ignores_missing_outcome() -> None:
    sig = MacroSurpriseSignal(min_train=1)
    sig.observe(_Ev(abnormal_return=None, macro_surprise=0.5))  # delisted -> not learned
    assert sig.predict(_Ev(macro_surprise=0.5)) is None


# ---------------------------------------------------------------------------
# CombinedSignal — equal-weight mean of constituent expected-return models
# ---------------------------------------------------------------------------


def test_combined_averages_constituent_estimates() -> None:
    a = EventTypeSignal(min_train=1)
    b = MacroSurpriseSignal(min_train=1)
    combined = CombinedSignal([a, b])
    combined.observe(_Ev("earnings", 0.02, macro_surprise=0.5))  # both learn
    # a("earnings") -> 0.02 ; b(+regime) -> 0.02 ; mean -> 0.02
    assert combined.predict(_Ev("earnings", macro_surprise=0.5)) == pytest.approx(0.02)


def test_combined_uses_available_when_one_abstains() -> None:
    a = EventTypeSignal(min_train=1)
    b = MacroSurpriseSignal(min_train=1)
    combined = CombinedSignal([a, b])
    combined.observe(_Ev("earnings", 0.04, macro_surprise=None))  # only a learns
    # b has no macro history -> abstains; combined falls back to a's 0.04.
    assert combined.predict(_Ev("earnings", macro_surprise=None)) == pytest.approx(0.04)


def test_combined_none_when_all_abstain() -> None:
    combined = CombinedSignal([EventTypeSignal(min_train=1), MacroSurpriseSignal(min_train=1)])
    assert combined.predict(_Ev("never_seen", macro_surprise=None)) is None


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
    assert isinstance(
        make_signal_model("significant_event_type", min_train=3), SignificantEventTypeSignal
    )
    assert isinstance(make_signal_model("macro_surprise", min_train=3), MacroSurpriseSignal)
    assert isinstance(make_signal_model("combined", min_train=3), CombinedSignal)
    assert isinstance(make_signal_model("llm_direction", min_train=3), DirectionSignal)


def test_factory_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="unknown signal model"):
        make_signal_model("nope", min_train=3)


def test_registered_model_names() -> None:
    assert SIGNAL_MODEL_NAMES == (
        "event_type_history",
        "significant_event_type",
        "macro_surprise",
        "combined",
        "llm_direction",
    )
