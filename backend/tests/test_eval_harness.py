"""Tests for eval.goldset loading and eval.harness (with a stub extractor)."""

from __future__ import annotations

import json

import pytest

from markettrace.eval.goldset import GoldExample, load_goldset
from markettrace.eval.harness import Prediction, evaluate


def test_load_seed_goldset() -> None:
    """The bundled seed gold set loads and validates."""
    examples = load_goldset()
    assert len(examples) >= 5
    assert all(isinstance(e, GoldExample) for e in examples)
    ids = [e.id for e in examples]
    assert len(ids) == len(set(ids))  # ids unique


def test_load_goldset_missing_field(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"id": "x", "text": "t"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        load_goldset(bad)


def test_load_goldset_duplicate_id(tmp_path) -> None:
    dup = tmp_path / "dup.json"
    record = {"id": "x", "text": "t", "gold_event_type": "earnings", "gold_entities": []}
    dup.write_text(json.dumps([record, record]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_goldset(dup)


def test_load_goldset_not_a_list(tmp_path) -> None:
    bad = tmp_path / "obj.json"
    bad.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON array"):
        load_goldset(bad)


def test_evaluate_perfect_predictions() -> None:
    goldset = [
        GoldExample("a", "t1", "earnings", {"AAPL"}),
        GoldExample("b", "t2", "buyback", {"MSFT"}),
    ]

    def predict(ex: GoldExample) -> Prediction:
        return Prediction(event_type=ex.gold_event_type, entities=set(ex.gold_entities))

    report = evaluate(goldset, predict)
    assert report.n_examples == 2
    assert report.classification.macro_f1 == pytest.approx(1.0)
    assert report.entity_linking.f1 == pytest.approx(1.0)


def test_evaluate_entity_matching_is_case_insensitive() -> None:
    goldset = [GoldExample("a", "t", "earnings", {"aapl"})]

    def predict(ex: GoldExample) -> Prediction:
        return Prediction(event_type="earnings", entities={"AAPL"})

    report = evaluate(goldset, predict)
    assert report.entity_linking.f1 == pytest.approx(1.0)


def test_evaluate_wrong_class_lowers_f1() -> None:
    goldset = [
        GoldExample("a", "t1", "earnings", {"AAPL"}),
        GoldExample("b", "t2", "buyback", {"MSFT"}),
    ]

    def predict(ex: GoldExample) -> Prediction:
        return Prediction(event_type="earnings", entities=set(ex.gold_entities))

    report = evaluate(goldset, predict)
    assert report.classification.accuracy == pytest.approx(0.5)


def test_canonical_scoring_collapses_synonyms() -> None:
    # Gold labels are canonical families; the extractor emits fragmented raw
    # types. Canonical scoring must count them as correct, while the raw score
    # (exact string) counts them as wrong.
    goldset = [
        GoldExample("a", "t1", "earnings", {"AAPL"}),
        GoldExample("b", "t2", "insider_trading", {"TSLA"}),
    ]
    raw_pred = {"a": "earnings_release", "b": "insider_sale"}

    def predict(ex: GoldExample) -> Prediction:
        return Prediction(event_type=raw_pred[ex.id], entities=set(ex.gold_entities))

    report = evaluate(goldset, predict)
    # Canonical: earnings_release -> earnings, insider_sale -> insider_trading.
    assert report.classification.accuracy == pytest.approx(1.0)
    assert report.classification.macro_f1 == pytest.approx(1.0)
    # Raw: exact strings never match the canonical gold labels.
    assert report.raw_classification.accuracy == pytest.approx(0.0)
