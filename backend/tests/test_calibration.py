"""Tests for confidence calibration of the directional call (Phase 4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from markettrace.db.models import Document, Event, EventImpact, Instrument
from markettrace.impact.calibration import (
    DEFAULT_CALIBRATION_BINS,
    calibrate,
    compute_confidence_calibration,
)

# ---------------------------------------------------------------------------
# calibrate — pure function over (confidence, direction, abnormal_return)
# ---------------------------------------------------------------------------


def test_empty_input_reports_none_stats_and_full_bin_grid() -> None:
    report = calibrate([], horizon_days=5)
    assert report.n_events_total == 0
    assert report.n_predictions == 0
    assert report.mean_confidence is None
    assert report.hit_rate is None
    assert report.expected_calibration_error is None
    assert report.brier_score is None
    # The bin grid is always present, every bin empty.
    assert len(report.bins) == DEFAULT_CALIBRATION_BINS
    assert all(b.count == 0 and b.hit_rate is None for b in report.bins)


def test_scores_direction_against_realised_sign() -> None:
    # positive dir + positive return = hit; positive dir + negative return = miss.
    report = calibrate(
        [(0.95, "positive", 0.01), (0.91, "positive", -0.02)],
        horizon_days=5,
    )
    assert report.n_predictions == 2
    assert report.hit_rate == pytest.approx(0.5)
    # Both land in the top bin [0.9, 1.0].
    top = report.bins[-1]
    assert top.count == 2
    assert top.mean_confidence == pytest.approx((0.95 + 0.91) / 2)
    assert top.hit_rate == pytest.approx(0.5)
    assert top.gap == pytest.approx((0.95 + 0.91) / 2 - 0.5)


def test_negative_direction_hits_on_negative_return() -> None:
    report = calibrate(
        [(0.8, "negative", -0.03), (0.8, "negative", 0.03)],
        horizon_days=5,
    )
    assert report.n_predictions == 2
    assert report.hit_rate == pytest.approx(0.5)


def test_neutral_and_missing_outcomes_excluded_and_counted() -> None:
    report = calibrate(
        [
            (0.9, "neutral", 0.01),   # neutral -> not a directional call
            (0.9, None, 0.01),        # no direction -> not a call
            (0.9, "positive", None),  # missing return
            (0.9, "positive", 0.0),   # exactly-zero return has no sign
            (0.9, "positive", 0.02),  # the only scored prediction
        ],
        horizon_days=5,
    )
    assert report.n_events_total == 5
    assert report.n_dropped_neutral == 2
    assert report.n_dropped_no_outcome == 2
    assert report.n_predictions == 1
    assert report.hit_rate == pytest.approx(1.0)


def test_confidence_is_clamped_into_range() -> None:
    # conf 1.5 clamps to 1.0 (top bin), -0.2 clamps to 0.0 (first bin).
    report = calibrate(
        [(1.5, "positive", 0.01), (-0.2, "positive", 0.01)],
        horizon_days=5,
    )
    assert report.bins[-1].count == 1
    assert report.bins[-1].mean_confidence == pytest.approx(1.0)
    assert report.bins[0].count == 1
    assert report.bins[0].mean_confidence == pytest.approx(0.0)


def test_confidence_exactly_one_lands_in_final_bin() -> None:
    report = calibrate([(1.0, "positive", 0.01)], horizon_days=5)
    assert report.bins[-1].count == 1
    assert sum(b.count for b in report.bins) == 1


def test_overconfident_band_has_positive_gap() -> None:
    # Four predictions at conf 0.9, only half correct -> overconfident (gap > 0).
    report = calibrate(
        [
            (0.9, "positive", 0.01),
            (0.9, "positive", 0.01),
            (0.9, "positive", -0.01),
            (0.9, "positive", -0.01),
        ],
        horizon_days=5,
    )
    top = report.bins[-1]
    assert top.hit_rate == pytest.approx(0.5)
    assert top.gap == pytest.approx(0.4)
    assert report.expected_calibration_error == pytest.approx(0.4)


def test_perfect_calibration_has_zero_ece() -> None:
    # Bin at 0.9 hits 9/10; bin at 0.5 hits 5/10. Each bin's mean == its hit rate.
    preds = (
        [(0.9, "positive", 0.01)] * 9
        + [(0.9, "positive", -0.01)] * 1
        + [(0.5, "positive", 0.01)] * 5
        + [(0.5, "positive", -0.01)] * 5
    )
    report = calibrate(preds, horizon_days=5)
    assert report.expected_calibration_error == pytest.approx(0.0, abs=1e-9)


def test_brier_score_matches_definition() -> None:
    report = calibrate(
        [(0.8, "positive", 0.01), (0.3, "positive", -0.01)],
        horizon_days=5,
    )
    # correct=1 for the first (0.8), correct=0 for the second (0.3).
    expected = ((0.8 - 1.0) ** 2 + (0.3 - 0.0) ** 2) / 2
    assert report.brier_score == pytest.approx(expected)


def test_rejects_non_positive_bin_count() -> None:
    with pytest.raises(ValueError, match="n_bins"):
        calibrate([], horizon_days=5, n_bins=0)


def test_custom_bin_count_partitions_range() -> None:
    report = calibrate([(0.55, "positive", 0.01)], horizon_days=5, n_bins=2)
    assert len(report.bins) == 2
    # 0.55 -> int(0.55 * 2) = 1 -> the [0.5, 1.0] bin.
    assert report.bins[1].count == 1
    assert report.bins[0].count == 0


# ---------------------------------------------------------------------------
# compute_confidence_calibration — session helper
# ---------------------------------------------------------------------------


def _seed_event(
    session: Session,
    inst: Instrument,
    *,
    day: int,
    confidence: float,
    direction: str,
    abnormal_return: float | None,
    horizon_days: int = 5,
) -> None:
    doc = Document(
        source="sec_edgar",
        external_id=f"acc-{day}-{horizon_days}",
        url="https://example.com",
        title="8-K",
        content_hash=f"h{day}-{horizon_days}",
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
        direction=direction,
        horizon_days=horizon_days,
        confidence=confidence,
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
            direction=direction,
            horizon_days=horizon_days,
            abnormal_return=abnormal_return,
            computed_at=datetime(2026, 1, day, tzinfo=UTC),
        )
    )


def test_compute_confidence_calibration_joins_event_confidence(
    db_session: Session,
) -> None:
    inst = Instrument(market="US", ticker="AAPL", name="Apple")
    db_session.add(inst)
    db_session.flush()

    # At horizon 5: two correct, one wrong -> hit_rate 2/3.
    _seed_event(db_session, inst, day=1, confidence=0.9, direction="positive", abnormal_return=0.01)
    _seed_event(db_session, inst, day=2, confidence=0.8, direction="positive", abnormal_return=0.02)
    _seed_event(db_session, inst, day=3, confidence=0.7, direction="positive", abnormal_return=-0.01)
    db_session.commit()

    reports = compute_confidence_calibration(db_session, horizons=[5, 20])
    by_h = {r.horizon_days: r for r in reports}

    assert by_h[5].n_predictions == 3
    assert by_h[5].hit_rate == pytest.approx(2 / 3)
    assert by_h[5].mean_confidence == pytest.approx((0.9 + 0.8 + 0.7) / 3)
    # No events seeded at horizon 20 -> an empty (but present) report.
    assert by_h[20].n_predictions == 0
    assert by_h[20].hit_rate is None
