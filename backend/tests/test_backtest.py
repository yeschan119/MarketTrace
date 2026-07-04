"""Tests for the walk-forward event-impact backtest (look-ahead blocked)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as _date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.db.models import (
    Base,
    Document,
    Event,
    EventImpact,
    Instrument,
    MacroObservation,
    Price,
)
from markettrace.impact.backtest import (
    BacktestEvent,
    _load_backtest_events,
    distinct_macro_series,
    run_macro_decomposition,
    run_walk_forward_backtest,
    walk_forward_backtest,
)
from markettrace.impact.signal import DirectionSignal


def _ev(day: int, event_type: str, ar: float | None) -> BacktestEvent:
    return BacktestEvent(
        occurred_at=datetime(2026, 1, day, tzinfo=UTC),
        event_type=event_type,
        abnormal_return=ar,
    )


def _dir_ev(day: int, direction: str, ar: float | None) -> BacktestEvent:
    return BacktestEvent(
        occurred_at=datetime(2026, 1, day, tzinfo=UTC),
        event_type="x",
        abnormal_return=ar,
        direction=direction,
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
    assert result.mean_strategy_return_net is None
    assert result.information_coefficient is None


# ---------------------------------------------------------------------------
# Trading costs (commission + slippage) — mean_strategy_return_net
# ---------------------------------------------------------------------------


def test_net_equals_gross_when_costs_are_zero() -> None:
    events = [_ev(d, "earnings", 0.02) for d in range(1, 8)]
    result = walk_forward_backtest(events, horizon_days=5, min_train_per_type=3)
    assert result.commission_per_trade == 0.0
    assert result.slippage_per_trade == 0.0
    assert result.mean_strategy_return_net == result.mean_strategy_return


def test_costs_reduce_net_by_round_trip_on_every_entered_position() -> None:
    # 4 predictions, all entered (sign != 0). Round-trip cost = 0.001 + 0.0005.
    events = [_ev(d, "earnings", 0.02) for d in range(1, 8)]
    result = walk_forward_backtest(
        events,
        horizon_days=5,
        min_train_per_type=3,
        commission_per_trade=0.001,
        slippage_per_trade=0.0005,
    )
    assert result.n_predictions == 4
    assert result.mean_strategy_return == pytest.approx(0.02)
    # Every one of the 4 predictions is a +ve position -> full round-trip cost each.
    assert result.mean_strategy_return_net == pytest.approx(0.02 - 0.0015)


def test_flat_signal_positions_pay_no_cost() -> None:
    # A type whose prior mean is exactly 0 -> predicted sign 0 -> no position, no cost.
    events = [_ev(1, "x", 0.02), _ev(2, "x", -0.02), _ev(3, "x", 0.03), _ev(4, "x", -0.03)]
    result = walk_forward_backtest(
        events,
        horizon_days=1,
        min_train_per_type=2,
        commission_per_trade=0.01,
        slippage_per_trade=0.01,
    )
    # Predictions for events 3 and 4. Event 3 prior mean = (0.02-0.02)/2 = 0 -> flat.
    # Event 4 prior mean = (0.02-0.02+0.03)/3 > 0 -> entered, pays cost.
    assert result.n_predictions == 2
    # Only one position entered -> net = gross - (1/2)*round_trip_cost.
    round_trip = 0.02
    assert result.mean_strategy_return_net == pytest.approx(
        result.mean_strategy_return - round_trip / 2
    )


# ---------------------------------------------------------------------------
# Coverage honesty — delisted/halted events (missing outcome) are counted
# ---------------------------------------------------------------------------


def test_missing_outcomes_are_counted_not_hidden() -> None:
    # Two of five events have no realised return (e.g. delisted/halted over horizon).
    events = [
        _ev(1, "x", 0.02),
        _ev(2, "x", None),
        _ev(3, "x", 0.02),
        _ev(4, "x", None),
        _ev(5, "x", 0.02),
    ]
    result = walk_forward_backtest(events, horizon_days=1, min_train_per_type=2)
    assert result.n_events_total == 5
    assert result.n_dropped_no_outcome == 2
    assert result.n_events == 3
    assert result.n_events_total == result.n_events + result.n_dropped_no_outcome


def test_no_missing_outcomes_reports_zero_dropped() -> None:
    events = [_ev(d, "x", 0.01 * d) for d in range(1, 5)]
    result = walk_forward_backtest(events, horizon_days=1, min_train_per_type=2)
    assert result.n_dropped_no_outcome == 0
    assert result.n_events_total == result.n_events == 4


# ---------------------------------------------------------------------------
# Model selection & the DirectionSignal (LLM direction as a t=0 signal)
# ---------------------------------------------------------------------------


def test_default_model_is_event_type_history() -> None:
    result = walk_forward_backtest([_ev(1, "x", 0.02)], horizon_days=1)
    assert result.model == "event_type_history"


def test_direction_signal_scores_from_t0_with_no_training() -> None:
    events = [
        _dir_ev(1, "positive", 0.03),   # long, +ve realised -> hit, +0.03
        _dir_ev(2, "positive", -0.02),  # long, -ve realised -> miss, -0.02
        _dir_ev(3, "negative", -0.04),  # short, -ve realised -> hit, +0.04
        _dir_ev(4, "neutral", 0.10),    # flat -> no position, contributes 0
    ]
    result = walk_forward_backtest(events, horizon_days=1, model=DirectionSignal())
    assert result.model == "llm_direction"
    # Every event yields a call from day 1 (no training gate).
    assert result.n_predictions == 4
    # Neutral is excluded from directional hit rate; 2 of the 3 directional hit.
    assert result.hit_rate == pytest.approx(2 / 3)
    # (0.03 - 0.02 + 0.04 + 0) / 4
    assert result.mean_strategy_return == pytest.approx(0.0125)


def test_direction_signal_costs_only_hit_entered_positions() -> None:
    events = [
        _dir_ev(1, "positive", 0.03),
        _dir_ev(2, "neutral", 0.10),  # flat -> pays no cost
    ]
    result = walk_forward_backtest(
        events,
        horizon_days=1,
        model=DirectionSignal(),
        commission_per_trade=0.001,
        slippage_per_trade=0.001,
    )
    # 2 predictions, only 1 entered (the positive). Round-trip cost = 0.002.
    assert result.n_predictions == 2
    # gross = (0.03 + 0) / 2 = 0.015 ; net = (0.03 - 0.002 + 0) / 2
    assert result.mean_strategy_return == pytest.approx(0.015)
    assert result.mean_strategy_return_net == pytest.approx((0.03 - 0.002) / 2)


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


def test_macro_enrichment_is_look_ahead_safe(mem_session) -> None:
    """Each event's macro_surprise is the latest surprise published STRICTLY before it."""
    inst = Instrument(market="US", ticker="AAPL", name="Apple")
    mem_session.add(inst)
    mem_session.flush()

    # One macro surprise released on Jan 2. Events on Jan 1..4 share the fixture shape.
    mem_session.add(
        MacroObservation(
            series_id="CPIAUCSL",
            source="fred",
            reference_date=datetime(2025, 12, 1, tzinfo=UTC),
            released_value=1.0,
            surprise_score=0.7,
            occurred_at=datetime(2025, 12, 1, tzinfo=UTC),
            first_seen_at=datetime(2026, 1, 2, tzinfo=UTC),
            published_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
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

    events = _load_backtest_events(mem_session, horizon_days=5)
    by_day = {e.occurred_at.day: e.macro_surprise for e in events}
    assert by_day[1] is None  # nothing published before Jan 1
    assert by_day[2] is None  # STRICTLY before -> the Jan-2 release itself is excluded
    assert by_day[3] == pytest.approx(0.7)  # sees the Jan-2 surprise
    assert by_day[4] == pytest.approx(0.7)


def test_pre_event_momentum_is_look_ahead_safe(mem_session) -> None:
    """pre_event_momentum uses only prices dated strictly before the event."""
    inst = Instrument(market="US", ticker="AAPL", name="Apple")
    mem_session.add(inst)
    mem_session.flush()

    # 25 trading days of prices rising 1/day, then a jump on the event day itself.
    for i in range(25):
        mem_session.add(
            Price(
                instrument_id=inst.id,
                date=_date(2026, 1, 1) + timedelta(days=i),
                open=100.0 + i,
                high=100.0 + i,
                low=100.0 + i,
                close=100.0 + i,
                adj_close=100.0 + i,
                volume=1000.0,
            )
        )
    # Event on 2026-01-25 (i=24, adj_close 124). Window=20 → uses price 20 trading
    # days before the last pre-event close, never the event-day price.
    event_day = datetime(2026, 1, 25, tzinfo=UTC)
    doc = Document(
        source="sec_edgar",
        external_id="acc-1",
        url="https://example.com",
        title="8-K",
        content_hash="h1",
        market="US",
        published_at=event_day,
        first_seen_at=event_day,
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
        analyzed_at=event_day,
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
            computed_at=event_day,
        )
    )
    mem_session.commit()

    (loaded,) = _load_backtest_events(mem_session, horizon_days=5)
    # Last close strictly before the event = 2026-01-24 (adj 123, i=23). Twenty
    # trading days earlier = i=3 (adj 103). Momentum = 123/103 - 1.
    assert loaded.pre_event_momentum == pytest.approx(123.0 / 103.0 - 1.0)


def _seed_two_series(session) -> None:
    """One instrument, 4 earnings events (Jan 3..6, h=5), and two macro series
    with OPPOSITE-sign surprises both released Jan 2 (so events 3..6 see both)."""
    inst = Instrument(market="US", ticker="AAPL", name="Apple")
    session.add(inst)
    session.flush()
    for series_id, surprise in (("CPIAUCSL", 0.9), ("UNRATE", -0.4)):
        session.add(
            MacroObservation(
                series_id=series_id,
                source="fred",
                reference_date=datetime(2025, 12, 1, tzinfo=UTC),
                released_value=1.0,
                surprise_score=surprise,
                occurred_at=datetime(2025, 12, 1, tzinfo=UTC),
                first_seen_at=datetime(2026, 1, 2, tzinfo=UTC),
                published_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
    for day in range(3, 7):
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
        session.add(doc)
        session.flush()
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
        session.add(event)
        session.flush()
        session.add(
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
    session.commit()


def test_load_backtest_events_scopes_regime_to_one_series(mem_session) -> None:
    _seed_two_series(mem_session)
    cpi = {e.occurred_at.day: e.macro_surprise for e in
           _load_backtest_events(mem_session, horizon_days=5, macro_series="CPIAUCSL")}
    unrate = {e.occurred_at.day: e.macro_surprise for e in
              _load_backtest_events(mem_session, horizon_days=5, macro_series="UNRATE")}
    # Each event sees only the requested series' (opposite-sign) surprise.
    assert cpi[3] == pytest.approx(0.9)
    assert unrate[3] == pytest.approx(-0.4)


def test_distinct_macro_series_lists_series_with_surprise(mem_session) -> None:
    _seed_two_series(mem_session)
    assert distinct_macro_series(mem_session) == ["CPIAUCSL", "UNRATE"]


def test_macro_decomposition_returns_row_per_series_and_horizon(mem_session) -> None:
    _seed_two_series(mem_session)
    rows = run_macro_decomposition(mem_session, horizons=[5])
    assert {r.series_id for r in rows} == {"CPIAUCSL", "UNRATE"}
    assert all(r.horizon_days == 5 for r in rows)
