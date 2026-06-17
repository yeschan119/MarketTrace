"""Tests for event-type significance (one-sample two-sided t-test, no SciPy)."""

from __future__ import annotations

import pytest

from markettrace.impact.significance import (
    MIN_SAMPLE,
    assess_significance,
    compute_event_type_significance,
    two_sided_t_pvalue,
)
from markettrace.impact.statistics import EventTypeStat

# ---------------------------------------------------------------------------
# two_sided_t_pvalue — validated against known reference values
# ---------------------------------------------------------------------------


def test_pvalue_t_zero_is_one() -> None:
    # t = 0 -> the mean sits exactly at H0; two-sided p-value is 1.0.
    assert two_sided_t_pvalue(0.0, 10) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize(
    ("t_stat", "df", "expected"),
    [
        (2.228, 10, 0.05),   # t_0.025,10  ~= 2.228 -> two-sided p ~= 0.05
        (2.0, 10, 0.0734),   # reference (scipy: 0.073388)
        (3.169, 10, 0.01),   # t_0.005,10 ~= 3.169 -> p ~= 0.01
        (1.0, 1, 0.5),       # Cauchy (df=1): P(|T|>1) = 0.5
    ],
)
def test_pvalue_reference_points(t_stat: float, df: int, expected: float) -> None:
    assert two_sided_t_pvalue(t_stat, df) == pytest.approx(expected, abs=2e-3)


def test_pvalue_symmetric_in_sign() -> None:
    assert two_sided_t_pvalue(2.5, 7) == pytest.approx(two_sided_t_pvalue(-2.5, 7))


def test_pvalue_none_when_df_nonpositive() -> None:
    assert two_sided_t_pvalue(3.0, 0) is None


# ---------------------------------------------------------------------------
# assess_significance — verdicts + sample gating
# ---------------------------------------------------------------------------


def _stat(event_type: str, n: int, mean: float | None, std: float | None) -> EventTypeStat:
    return EventTypeStat(
        event_type=event_type,
        horizon_days=1,
        count=n,
        mean_abnormal_return=mean,
        std_abnormal_return=std,
    )


def test_single_observation_is_inconclusive() -> None:
    # n=1: no std, no t-stat, never significant, never sufficient.
    result = assess_significance(_stat("board_appointment", 1, 0.12, None))
    assert result.t_stat is None
    assert result.p_value is None
    assert result.significant_5pct is False
    assert result.sufficient_sample is False


def test_small_sample_not_significant_even_if_extreme() -> None:
    # n=3 (< MIN_SAMPLE): a t-stat can be computed but the verdict is gated off.
    result = assess_significance(_stat("management_change", 3, 0.05, 0.01))
    assert result.t_stat is not None
    assert result.sufficient_sample is False
    assert result.significant_5pct is False


def test_adequate_sample_strong_effect_is_significant() -> None:
    # n=30, mean 2% with 1% std -> t ~= 10.95 -> clearly significant.
    result = assess_significance(_stat("earnings_beat", 30, 0.02, 0.01))
    assert result.sufficient_sample is True
    assert result.t_stat == pytest.approx(0.02 / (0.01 / 30**0.5), rel=1e-9)
    assert result.p_value is not None and result.p_value < 0.05
    assert result.significant_5pct is True


def test_adequate_sample_noise_is_not_significant() -> None:
    # Mirrors production earnings_release: n=13, mean -1% with 4.3% std -> |t|<1.
    result = assess_significance(_stat("earnings_release", 13, -0.00996, 0.04282))
    assert result.sufficient_sample is True
    assert abs(result.t_stat) < 1.0
    assert result.p_value is not None and result.p_value > 0.05
    assert result.significant_5pct is False


def test_zero_dispersion_yields_no_test() -> None:
    # std == 0 (identical observations) -> t-stat undefined; report no test.
    result = assess_significance(_stat("dividend", 6, 0.01, 0.0))
    assert result.t_stat is None
    assert result.significant_5pct is False


def test_min_sample_boundary() -> None:
    assert assess_significance(_stat("x", MIN_SAMPLE - 1, 0.01, 0.01)).sufficient_sample is False
    assert assess_significance(_stat("x", MIN_SAMPLE, 0.01, 0.01)).sufficient_sample is True


# ---------------------------------------------------------------------------
# compute_event_type_significance — DB integration (in-memory)
# ---------------------------------------------------------------------------


def test_compute_from_session(monkeypatch) -> None:
    fake_stats = [
        _stat("earnings_release", 13, -0.00996, 0.04282),
        _stat("board_appointment", 2, 0.03, 0.017),
    ]
    monkeypatch.setattr(
        "markettrace.impact.significance.compute_event_type_statistics",
        lambda session: fake_stats,
    )

    results = compute_event_type_significance(session=object())

    assert [r.event_type for r in results] == ["earnings_release", "board_appointment"]
    assert results[0].sufficient_sample is True
    assert results[1].sufficient_sample is False
