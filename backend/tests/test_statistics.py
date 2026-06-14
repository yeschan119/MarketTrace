"""Tests for impact.statistics: event-type reaction aggregation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from markettrace.db.models import EventImpact
from markettrace.impact.statistics import (
    aggregate_reactions,
    compute_event_type_statistics,
)


def test_aggregate_basic_mean_and_std() -> None:
    records = [
        ("earnings", 1, 0.02),
        ("earnings", 1, 0.04),
        ("earnings", 1, 0.06),
    ]
    stats = aggregate_reactions(records)
    assert len(stats) == 1
    s = stats[0]
    assert s.event_type == "earnings"
    assert s.horizon_days == 1
    assert s.count == 3
    assert s.mean_abnormal_return == pytest.approx(0.04)
    # sample std of [0.02, 0.04, 0.06] = 0.02
    assert s.std_abnormal_return == pytest.approx(0.02)


def test_aggregate_ignores_none() -> None:
    records = [("earnings", 5, None), ("earnings", 5, 0.10), ("earnings", 5, None)]
    stats = aggregate_reactions(records)
    s = stats[0]
    assert s.count == 1
    assert s.mean_abnormal_return == pytest.approx(0.10)
    # only one observation -> std undefined
    assert s.std_abnormal_return is None


def test_aggregate_all_none_bucket_kept_with_zero_count() -> None:
    stats = aggregate_reactions([("lawsuit", 20, None)])
    s = stats[0]
    assert s.count == 0
    assert s.mean_abnormal_return is None
    assert s.std_abnormal_return is None


def test_aggregate_buckets_sorted() -> None:
    records = [
        ("buyback", 5, 0.01),
        ("earnings", 1, 0.02),
        ("earnings", 5, 0.03),
    ]
    stats = aggregate_reactions(records)
    keys = [(s.event_type, s.horizon_days) for s in stats]
    assert keys == [("buyback", 5), ("earnings", 1), ("earnings", 5)]


def test_compute_event_type_statistics_from_db(db_session: Session) -> None:
    now = datetime(2026, 6, 14, tzinfo=UTC)
    db_session.add_all(
        [
            EventImpact(
                event_id=1,
                instrument_id=1,
                event_type="earnings",
                industry="Tech",
                direction="positive",
                horizon_days=1,
                abnormal_return=0.02,
                signed_abnormal_return=0.02,
                computed_at=now,
            ),
            EventImpact(
                event_id=2,
                instrument_id=1,
                event_type="earnings",
                industry="Tech",
                direction="positive",
                horizon_days=1,
                abnormal_return=0.04,
                signed_abnormal_return=0.04,
                computed_at=now,
            ),
        ]
    )
    db_session.commit()

    stats = compute_event_type_statistics(db_session)
    assert len(stats) == 1
    assert stats[0].event_type == "earnings"
    assert stats[0].count == 2
    assert stats[0].mean_abnormal_return == pytest.approx(0.03)
