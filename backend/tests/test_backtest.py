"""Tests for the walk-forward event-impact backtest (look-ahead blocked)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.db.models import Base, Document, Event, EventImpact, Instrument
from markettrace.impact.backtest import (
    BacktestEvent,
    run_walk_forward_backtest,
    walk_forward_backtest,
)


def _ev(day: int, event_type: str, ar: float | None) -> BacktestEvent:
    return BacktestEvent(
        occurred_at=datetime(2026, 1, day, tzinfo=UTC),
        event_type=event_type,
        abnormal_return=ar,
    )


def test_no_predictions_below_min_train() -> None:
    # 3 events, min_train=3 -> no event ever has 3 PRIOR observations.
    events = [_ev(1, "earnings", 0.01), _ev(2, "earnings", 0.02), _ev(3, "earnings", 0.03)]
    result = walk_forward_backtest(events, horizon_days=5, min_train_per_type=3)
    assert result.n_events == 3
    assert result.n_predictions == 0
    assert result.hit_rate is None
    assert result.information_coefficient is None


def test_predictions_start_after_min_train() -> None:
    # min_train=2 -> 3rd and 4th events are predicted (2+ priors).
    events = [
        _ev(1, "earnings", 0.01),
        _ev(2, "earnings", 0.02),
        _ev(3, "earnings", 0.03),
        _ev(4, "earnings", 0.04),
    ]
    result = walk_forward_backtest(events, horizon_days=5, min_train_per_type=2)
    assert result.n_predictions == 2


def test_perfect_positive_persistence_hits_every_time() -> None:
    # A type that is always +ve: once trained, every prediction is +ve and correct.
    events = [_ev(d, "earnings", 0.02) for d in range(1, 8)]
    result = walk_forward_backtest(events, horizon_days=5, min_train_per_type=3)
    assert result.n_predictions == 4
    assert result.hit_rate == 1.0
    # Strategy goes long (+1) on a +2% realised move every time.
    assert result.mean_strategy_return == 0.02


def test_sign_flip_is_a_miss() -> None:
    # Train +ve, then realised goes -ve -> predicted sign +, realised sign - -> miss.
    events = [_ev(1, "x", 0.02), _ev(2, "x", 0.02), _ev(3, "x", 0.02), _ev(4, "x", -0.05)]
    result = walk_forward_backtest(events, horizon_days=1, min_train_per_type=3)
    assert result.n_predictions == 1
    assert result.hit_rate == 0.0
    # sign(predicted)=+1, realised=-0.05 -> strategy return = -0.05.
    assert result.mean_strategy_return == -0.05


def test_look_ahead_is_blocked() -> None:
    """A prediction must never see its own or any future outcome.

    History is all +0.02 except the LAST event which is a huge -1.0 outlier. If
    look-ahead leaked, the training mean would be dragged negative; because the
    outlier is scored before being added to history, every prediction stays +ve.
    """
    events = [_ev(d, "x", 0.02) for d in range(1, 6)] + [_ev(6, "x", -1.0)]
    result = walk_forward_backtest(events, horizon_days=1, min_train_per_type=3)
    # Predictions for days 4,5,6. Days 4&5 hit (+), day 6 (-1.0 realised) misses.
    assert result.n_predictions == 3
    assert result.hit_rate == 2 / 3
    # If the -1.0 had leaked into its own training mean, day 6's predicted sign
    # could flip; it must not. The training mean seen by day 6 is +0.02 (>0).


def test_unordered_input_is_sorted_by_date() -> None:
    ordered = [_ev(d, "x", 0.01 * d) for d in range(1, 6)]
    shuffled = [ordered[3], ordered[0], ordered[4], ordered[2], ordered[1]]
    assert walk_forward_backtest(
        shuffled, horizon_days=1, min_train_per_type=2
    ) == walk_forward_backtest(ordered, horizon_days=1, min_train_per_type=2)


def test_none_abnormal_returns_dropped() -> None:
    events = [_ev(1, "x", 0.02), _ev(2, "x", None), _ev(3, "x", 0.02), _ev(4, "x", 0.02)]
    result = walk_forward_backtest(events, horizon_days=1, min_train_per_type=2)
    # Only 3 usable events; with min_train=2 the 3rd usable one is predicted.
    assert result.n_events == 3
    assert result.n_predictions == 1


def test_information_coefficient_positive_when_predictions_track_outcomes() -> None:
    # Two types with distinct, persistent magnitudes -> predicted tracks realised.
    events = []
    for d in range(1, 7):
        events.append(_ev(d, "big", 0.05))
    for d in range(7, 13):
        events.append(_ev(d, "small", 0.005))
    result = walk_forward_backtest(events, horizon_days=1, min_train_per_type=3)
    assert result.information_coefficient is not None
    # Constant-within-type but different across types -> still positively correlated.
    assert result.information_coefficient > 0.0


def test_empty_input() -> None:
    result = walk_forward_backtest([], horizon_days=5, min_train_per_type=3)
    assert result.n_events == 0
    assert result.n_predictions == 0
    assert result.hit_rate is None
    assert result.mean_strategy_return is None
    assert result.information_coefficient is None


# ---------------------------------------------------------------------------
# run_walk_forward_backtest — DB integration (orders by filing date, no network)
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_run_backtest_joins_and_orders_by_filing_date(mem_session) -> None:
    inst = Instrument(market="US", ticker="AAPL", name="Apple")
    mem_session.add(inst)
    mem_session.flush()

    # Four "earnings" events on ascending filing dates, all +1% abnormal return.
    for day in range(1, 5):
        doc = Document(
            source="sec_edgar",
            external_id=f"acc-{day}",
            url="https://example.com",
            title="8-K",
            content_hash=f"h{day}",
            market="US",
            published_at=datetime(2026, 1, day, tzinfo=UTC),
            first_seen_at=datetime(2026, 1, day, tzinfo=UTC),
        )
        mem_session.add(doc)
        mem_session.flush()
        event = Event(
            document_id=doc.id,
            primary_instrument_id=inst.id,
            event_type="earnings",
            direction="positive",
            horizon_days=5,
            confidence=0.7,
            model="t",
            model_version="v1",
            analyzed_at=datetime(2026, 1, day, tzinfo=UTC),
        )
        mem_session.add(event)
        mem_session.flush()
        mem_session.add(
            EventImpact(
                event_id=event.id,
                instrument_id=inst.id,
                event_type="earnings",
                direction="positive",
                horizon_days=5,
                abnormal_return=0.01,
                computed_at=datetime(2026, 1, day, tzinfo=UTC),
            )
        )
    mem_session.commit()

    result = run_walk_forward_backtest(mem_session, horizon_days=5, min_train_per_type=2)

    assert result.n_events == 4
    assert result.n_predictions == 2  # events 3 and 4 have >= 2 priors
    assert result.hit_rate == 1.0
    assert result.mean_strategy_return == pytest.approx(0.01)
