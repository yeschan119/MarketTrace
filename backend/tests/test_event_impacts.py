"""Tests for impact.event_impacts: directional impact construction."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from markettrace.db.models import Event
from markettrace.impact.event_impacts import build_event_impacts, direction_sign
from markettrace.impact.returns import OutcomeResult

_NOW = datetime(2026, 6, 14, tzinfo=UTC)


def _event(direction: str) -> Event:
    return Event(
        id=7,
        document_id=1,
        primary_instrument_id=3,
        event_type="earnings_beat",
        direction=direction,
        horizon_days=20,
        confidence=0.8,
        model="claude-sonnet-4-6",
        model_version="2026-06-01",
        analyzed_at=_NOW,
    )


def test_direction_sign_mapping() -> None:
    assert direction_sign("positive") == 1
    assert direction_sign("negative") == -1
    assert direction_sign("neutral") == 0
    assert direction_sign("anything-else") == 0


def test_build_positive_direction_confirmed() -> None:
    outcomes = [OutcomeResult(horizon_days=1, raw_return=0.05, market_return=0.02, abnormal_return=0.03)]
    impacts = build_event_impacts(_event("positive"), outcomes, industry="Tech", computed_at=_NOW)
    assert len(impacts) == 1
    imp = impacts[0]
    assert imp.event_id == 7
    assert imp.instrument_id == 3
    assert imp.event_type == "earnings_beat"
    assert imp.industry == "Tech"
    assert imp.horizon_days == 1
    assert imp.abnormal_return == pytest.approx(0.03)
    assert imp.signed_abnormal_return == pytest.approx(0.03)  # positive * +1


def test_build_negative_direction_signs_flip() -> None:
    outcomes = [OutcomeResult(horizon_days=5, raw_return=-0.04, market_return=-0.01, abnormal_return=-0.03)]
    impacts = build_event_impacts(_event("negative"), outcomes, industry=None, computed_at=_NOW)
    # negative direction with a negative abnormal return -> confirmed -> positive signed
    assert impacts[0].signed_abnormal_return == pytest.approx(0.03)


def test_build_neutral_direction_is_zero() -> None:
    outcomes = [OutcomeResult(horizon_days=1, raw_return=0.05, market_return=0.02, abnormal_return=0.03)]
    impacts = build_event_impacts(_event("neutral"), outcomes, industry="Tech", computed_at=_NOW)
    assert impacts[0].signed_abnormal_return == pytest.approx(0.0)


def test_build_none_abnormal_return_propagates() -> None:
    outcomes = [OutcomeResult(horizon_days=60, raw_return=None, market_return=None, abnormal_return=None)]
    impacts = build_event_impacts(_event("positive"), outcomes, industry="Tech", computed_at=_NOW)
    assert impacts[0].abnormal_return is None
    assert impacts[0].signed_abnormal_return is None


def test_build_carries_sector_abnormal_return() -> None:
    outcomes = [
        OutcomeResult(
            horizon_days=1,
            raw_return=0.05,
            market_return=0.02,
            abnormal_return=0.03,
            sector_return=0.01,
            sector_abnormal_return=0.04,
        )
    ]
    impacts = build_event_impacts(_event("positive"), outcomes, industry="Tech", computed_at=_NOW)
    assert impacts[0].sector_abnormal_return == pytest.approx(0.04)


def test_build_one_impact_per_horizon() -> None:
    outcomes = [
        OutcomeResult(horizon_days=h, raw_return=0.01, market_return=0.0, abnormal_return=0.01)
        for h in (1, 5, 20, 60)
    ]
    impacts = build_event_impacts(_event("positive"), outcomes, industry="Tech", computed_at=_NOW)
    assert [i.horizon_days for i in impacts] == [1, 5, 20, 60]
