"""Tests for the offline live-sample scorer (deployed extractor vs. gold)."""

from __future__ import annotations

import json

from markettrace.eval.live_eval import score_live_sample
from markettrace.eval.taxonomy import CANONICAL_FAMILIES


def test_bundled_live_sample_scores_and_is_self_consistent() -> None:
    report = score_live_sample()
    # The bundled sample is a real stratified production sample.
    assert report.n_examples >= 30
    assert report.classification.support == report.n_examples
    # The bundled sample labels event-type families only; entity-linking labels
    # must be added explicitly before live entity F1 is meaningful.
    assert report.entity_linking is None
    assert report.n_entity_examples == 0
    # Every gold label is a valid canonical family.
    # (mismatches list only contains genuine stored != gold disagreements)
    for _eid, stored, gold in report.mismatches:
        assert stored != gold
        assert gold in CANONICAL_FAMILIES
        assert stored in CANONICAL_FAMILIES
    # Accuracy is consistent with the mismatch count.
    expected_acc = (report.n_examples - len(report.mismatches)) / report.n_examples
    assert abs(report.classification.accuracy - expected_acc) < 1e-9


def test_score_live_sample_custom_file(tmp_path) -> None:
    sample = {
        "examples": [
            # stored earnings_release canonicalises to earnings == gold -> match
            {
                "event_id": 1,
                "stored_event_type": "earnings_release",
                "gold_family": "earnings",
                "stored_ticker": "AAPL",
                "gold_ticker": "AAPL",
            },
            # stored product but gold investment -> mismatch
            {
                "event_id": 2,
                "stored_event_type": "product_launch",
                "gold_family": "investment",
                "stored_ticker": "MSFT",
                "gold_ticker": "NVDA",
            },
        ]
    }
    path = tmp_path / "s.json"
    path.write_text(json.dumps(sample), encoding="utf-8")

    report = score_live_sample(path)
    assert report.n_examples == 2
    assert report.classification.accuracy == 0.5
    assert report.mismatches == [(2, "product", "investment")]
    assert report.entity_linking is not None
    assert report.entity_linking.true_positives == 1
    assert report.entity_linking.false_positives == 1
    assert report.entity_linking.false_negatives == 1
    assert report.entity_linking.f1 == 0.5
    assert report.entity_mismatches == [(2, {"MSFT"}, {"NVDA"})]


def test_score_live_sample_accepts_bare_list(tmp_path) -> None:
    # Loader tolerates a top-level list as well as the {examples: [...]} wrapper.
    path = tmp_path / "list.json"
    path.write_text(
        json.dumps(
            [{"event_id": 9, "stored_event_type": "dividend_increase", "gold_family": "dividend"}]
        ),
        encoding="utf-8",
    )
    report = score_live_sample(path)
    assert report.n_examples == 1
    assert report.mismatches == []
