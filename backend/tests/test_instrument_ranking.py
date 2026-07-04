"""Tests for the confidence x recency weighted cross-instrument ranking."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from markettrace.impact.instrument_ranking import (
    RankingEventInput,
    rank_instruments,
)
from markettrace.impact.significance import EventTypeSignificance

AS_OF = date(2026, 7, 1)


def _sig(
    event_type: str,
    mean: float | None,
    *,
    horizon: int = 5,
    significant: bool = True,
    sufficient: bool = True,
    p_value: float | None = 0.001,
    count: int = 30,
) -> EventTypeSignificance:
    return EventTypeSignificance(
        event_type=event_type,
        horizon_days=horizon,
        count=count,
        mean_abnormal_return=mean,
        std_abnormal_return=0.02,
        t_stat=-5.0 if (mean or 0) < 0 else 5.0,
        p_value=p_value,
        significant_5pct=significant,
        sufficient_sample=sufficient,
    )


def _event(
    instrument_id: int,
    event_type: str,
    *,
    ticker: str = "AAA",
    name: str = "Alpha",
    market: str | None = "US",
    direction: str = "negative",
    confidence: float = 0.8,
    published: datetime | None = None,
    reviewed: datetime | None = None,
) -> RankingEventInput:
    return RankingEventInput(
        instrument_id=instrument_id,
        ticker=ticker,
        name=name,
        market=market,
        event_type=event_type,
        direction=direction,
        confidence=confidence,
        published_at=published or datetime(2026, 6, 1),
        reviewed_at=reviewed,
    )


# ---------------------------------------------------------------------------
# Basic aggregation + significance gate
# ---------------------------------------------------------------------------


def test_only_validated_event_types_contribute() -> None:
    significance = [_sig("insider_trading_report", -0.06)]
    events = [
        _event(1, "insider_trading_report"),
        _event(1, "insider_trading_report"),
        # governance has no significant row -> ignored entirely.
        _event(1, "governance_change"),
    ]
    ranked = rank_instruments(events, significance, AS_OF)
    assert len(ranked) == 1
    assert ranked[0].validated_count == 2
    assert ranked[0].weighted_score == pytest.approx(-0.06)
    assert ranked[0].simple_mean == pytest.approx(-0.06)
    assert ranked[0].lean == "bearish"


def test_insignificant_or_missing_mean_excluded() -> None:
    significance = [
        _sig("a", -0.06, significant=False),  # not significant
        _sig("b", None),  # no mean
        _sig("c", -0.04, sufficient=False),  # sample too small
    ]
    events = [_event(1, "a"), _event(1, "b"), _event(1, "c")]
    ranked = rank_instruments(events, significance, AS_OF)
    assert ranked == []


def test_min_validated_gate_drops_thin_instruments() -> None:
    significance = [_sig("earnings_release", -0.02)]
    events = [_event(1, "earnings_release")]  # only one validated event
    assert rank_instruments(events, significance, AS_OF) == []
    # A second validated event lifts it over the gate.
    events.append(_event(1, "earnings_release"))
    assert len(rank_instruments(events, significance, AS_OF)) == 1


def test_min_validated_configurable() -> None:
    significance = [_sig("earnings_release", -0.02)]
    events = [_event(1, "earnings_release")]
    assert len(rank_instruments(events, significance, AS_OF, min_validated=1)) == 1


# ---------------------------------------------------------------------------
# Weighting: recency + confidence
# ---------------------------------------------------------------------------


def test_recency_weight_favours_recent_events() -> None:
    # Two event types with opposite-magnitude validated drift. The recent one
    # should pull the weighted score toward its drift, away from the simple mean.
    significance = [_sig("recent_type", -0.10), _sig("old_type", -0.02)]
    events = [
        _event(
            1,
            "recent_type",
            direction="negative",
            published=datetime(2026, 6, 30),  # 1 day old
        ),
        _event(
            1,
            "old_type",
            direction="negative",
            published=datetime(2024, 6, 30),  # ~2 years old, heavily decayed
        ),
    ]
    ranked = rank_instruments(events, significance, AS_OF, half_life_days=180.0)
    r = ranked[0]
    # Simple mean is the midpoint -0.06; weighting toward the fresh -0.10 event
    # must drag the weighted score below the simple mean.
    assert r.simple_mean == pytest.approx(-0.06)
    assert r.weighted_score < r.simple_mean
    assert r.weighted_score < -0.09  # dominated by the recent -0.10


def test_confidence_weight_favours_confident_events() -> None:
    significance = [_sig("strong", -0.10), _sig("weak", -0.02)]
    same_day = datetime(2026, 6, 30)
    events = [
        _event(1, "strong", confidence=0.95, published=same_day),
        _event(1, "weak", confidence=0.10, published=same_day),
    ]
    ranked = rank_instruments(events, significance, AS_OF)
    # High-confidence -0.10 dominates the low-confidence -0.02.
    assert ranked[0].weighted_score < ranked[0].simple_mean
    assert ranked[0].weighted_score < -0.08


def test_as_of_determinism() -> None:
    significance = [_sig("t", -0.05), _sig("u", -0.01)]
    events = [
        _event(1, "t", published=datetime(2026, 1, 1)),
        _event(1, "u", published=datetime(2026, 6, 1)),
    ]
    a = rank_instruments(events, significance, date(2026, 7, 1))
    b = rank_instruments(events, significance, date(2026, 7, 1))
    assert a[0].weighted_score == b[0].weighted_score
    # A later as_of decays the older event more, shifting the score.
    c = rank_instruments(events, significance, date(2027, 7, 1))
    assert c[0].weighted_score != a[0].weighted_score


# ---------------------------------------------------------------------------
# Ordering across instruments
# ---------------------------------------------------------------------------


def test_sorted_ascending_by_weighted_score() -> None:
    significance = [_sig("harsh", -0.10), _sig("mild", -0.02)]
    events = [
        _event(1, "mild", ticker="MILD"),
        _event(1, "mild", ticker="MILD"),
        _event(2, "harsh", ticker="HARSH"),
        _event(2, "harsh", ticker="HARSH"),
    ]
    ranked = rank_instruments(events, significance, AS_OF)
    assert [r.instrument_id for r in ranked] == [2, 1]  # harsher caution first
    assert ranked[0].weighted_score < ranked[1].weighted_score


def test_tie_break_by_ticker() -> None:
    significance = [_sig("x", -0.05)]
    events = [
        _event(2, "x", ticker="ZULU"),
        _event(2, "x", ticker="ZULU"),
        _event(1, "x", ticker="ALFA"),
        _event(1, "x", ticker="ALFA"),
    ]
    ranked = rank_instruments(events, significance, AS_OF)
    # Equal scores -> ticker ascending.
    assert [r.ticker for r in ranked] == ["ALFA", "ZULU"]


def test_bullish_lean_when_validated_drift_positive() -> None:
    significance = [_sig("buyback", 0.03)]
    events = [
        _event(1, "buyback", direction="positive"),
        _event(1, "buyback", direction="positive"),
    ]
    ranked = rank_instruments(events, significance, AS_OF)
    assert ranked[0].lean == "bullish"
    assert ranked[0].weighted_score > 0


def test_neutral_lean_within_band() -> None:
    significance = [_sig("tiny", 0.002)]
    events = [_event(1, "tiny"), _event(1, "tiny")]
    ranked = rank_instruments(events, significance, AS_OF)
    assert ranked[0].lean == "neutral"


# ---------------------------------------------------------------------------
# Conflicts (LLM direction vs validated history) + top factor
# ---------------------------------------------------------------------------


def test_conflict_counts_direction_disagreement() -> None:
    # Validated drift is negative (down); an LLM "positive" read conflicts.
    significance = [_sig("insider_trading_report", -0.06)]
    events = [
        _event(1, "insider_trading_report", direction="positive", reviewed=None),
        _event(
            1,
            "insider_trading_report",
            direction="positive",
            reviewed=datetime(2026, 6, 20),
        ),
        _event(1, "insider_trading_report", direction="negative"),  # agrees
    ]
    ranked = rank_instruments(events, significance, AS_OF)
    r = ranked[0]
    assert r.conflict_count == 2
    assert r.unreviewed_conflict_count == 1  # one of the two is reviewed


def test_top_factor_is_strongest_drift_type() -> None:
    significance = [_sig("insider_trading_report", -0.06), _sig("earnings_release", -0.02)]
    events = [
        _event(1, "earnings_release"),
        _event(1, "earnings_release"),
        _event(1, "insider_trading_report"),
    ]
    ranked = rank_instruments(events, significance, AS_OF)
    tf = ranked[0].top_factor
    assert tf is not None
    assert tf.event_type == "insider_trading_report"  # -0.06 beats -0.02
    assert tf.drift == pytest.approx(-0.06)
    assert tf.count == 1


def test_empty_inputs() -> None:
    assert rank_instruments([], [_sig("x", -0.05)], AS_OF) == []
    assert rank_instruments([_event(1, "x")], [], AS_OF) == []
