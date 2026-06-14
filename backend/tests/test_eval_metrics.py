"""Tests for eval.metrics: P/R/F1, entity-linking, classification report."""

from __future__ import annotations

import pytest

from markettrace.eval.metrics import (
    classification_metrics,
    entity_linking_metrics,
    prf_from_counts,
)


def test_prf_perfect() -> None:
    prf = prf_from_counts(tp=4, fp=0, fn=0)
    assert prf.precision == pytest.approx(1.0)
    assert prf.recall == pytest.approx(1.0)
    assert prf.f1 == pytest.approx(1.0)


def test_prf_mixed() -> None:
    prf = prf_from_counts(tp=2, fp=2, fn=2)
    assert prf.precision == pytest.approx(0.5)
    assert prf.recall == pytest.approx(0.5)
    assert prf.f1 == pytest.approx(0.5)


def test_prf_zero_denominator_is_zero() -> None:
    prf = prf_from_counts(tp=0, fp=0, fn=0)
    assert prf.precision == 0.0
    assert prf.recall == 0.0
    assert prf.f1 == 0.0


def test_entity_linking_perfect() -> None:
    gold = {"d1": {"AAPL"}, "d2": {"MSFT", "GOOG"}}
    pred = {"d1": {"AAPL"}, "d2": {"MSFT", "GOOG"}}
    prf = entity_linking_metrics(gold, pred)
    assert prf.true_positives == 3
    assert prf.false_positives == 0
    assert prf.false_negatives == 0
    assert prf.f1 == pytest.approx(1.0)


def test_entity_linking_counts_fp_and_fn() -> None:
    gold = {"d1": {"AAPL"}, "d2": {"MSFT"}}
    pred = {"d1": {"AAPL", "TSLA"}, "d2": set()}
    prf = entity_linking_metrics(gold, pred)
    assert prf.true_positives == 1  # AAPL in d1
    assert prf.false_positives == 1  # TSLA in d1
    assert prf.false_negatives == 1  # MSFT in d2 missed


def test_entity_linking_document_only_in_one_side() -> None:
    gold = {"d1": {"AAPL"}}
    pred = {"d2": {"MSFT"}}
    prf = entity_linking_metrics(gold, pred)
    assert prf.true_positives == 0
    assert prf.false_positives == 1
    assert prf.false_negatives == 1


def test_classification_perfect_macro_f1() -> None:
    report = classification_metrics(["earnings", "buyback"], ["earnings", "buyback"])
    assert report.macro_f1 == pytest.approx(1.0)
    assert report.accuracy == pytest.approx(1.0)
    assert report.support == 2


def test_classification_partial() -> None:
    gold = ["earnings", "earnings", "buyback", "dividend"]
    pred = ["earnings", "buyback", "buyback", "dividend"]
    report = classification_metrics(gold, pred)
    # earnings: tp1 fp0 fn1 -> f1 = 2*1*0.5/1.5 = 0.6667
    assert report.per_class["earnings"].f1 == pytest.approx(2 / 3)
    # buyback: tp1 fp1 fn0 -> f1 = 2*0.5*1/1.5 = 0.6667
    assert report.per_class["buyback"].f1 == pytest.approx(2 / 3)
    # dividend: tp1 fp0 fn0 -> f1 = 1.0
    assert report.per_class["dividend"].f1 == pytest.approx(1.0)
    assert report.accuracy == pytest.approx(0.75)


def test_classification_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        classification_metrics(["a"], ["a", "b"])
