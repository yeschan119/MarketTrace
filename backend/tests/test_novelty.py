"""Tests for nlp.novelty: tokenization, similarity, novelty scoring, clustering."""

from __future__ import annotations

import pytest

from markettrace.nlp.novelty import (
    cluster_documents,
    jaccard_similarity,
    novelty_score,
    tokenize,
)


def test_tokenize_lowercases_and_splits() -> None:
    assert tokenize("Apple Q4, Revenue!") == {"apple", "q4", "revenue"}


def test_tokenize_empty_string() -> None:
    assert tokenize("") == set()


def test_jaccard_identical_texts() -> None:
    assert jaccard_similarity("record revenue beat", "record revenue beat") == pytest.approx(1.0)


def test_jaccard_disjoint_texts() -> None:
    assert jaccard_similarity("alpha beta", "gamma delta") == pytest.approx(0.0)


def test_jaccard_partial_overlap() -> None:
    # {a, b, c} vs {b, c, d}: intersection 2, union 4 -> 0.5
    assert jaccard_similarity("a b c", "b c d") == pytest.approx(0.5)


def test_jaccard_both_empty_is_identical() -> None:
    assert jaccard_similarity("", "") == pytest.approx(1.0)


def test_jaccard_empty_vs_nonempty_is_zero() -> None:
    assert jaccard_similarity("", "something") == pytest.approx(0.0)


def test_novelty_no_priors_is_fully_novel() -> None:
    assert novelty_score("a brand new story", []) == pytest.approx(1.0)


def test_novelty_exact_rehash_is_zero() -> None:
    prior = ["the company reported record revenue"]
    assert novelty_score("the company reported record revenue", prior) == pytest.approx(0.0)


def test_novelty_uses_max_similarity_across_priors() -> None:
    priors = ["totally unrelated text here", "a b c d"]
    # candidate {a,b,c,x} vs {a,b,c,d}: intersection 3, union 5 -> sim 0.6 -> novelty 0.4
    assert novelty_score("a b c x", priors) == pytest.approx(0.4)


def test_cluster_groups_near_duplicates() -> None:
    texts = [
        "Apple posted record quarterly revenue today",
        "Apple posted record quarterly revenue today, sources say",
        "Unrelated regulator announces new tariff schedule",
    ]
    clusters = cluster_documents(texts, threshold=0.5)
    # First two cluster together, the third stands alone.
    assert [0, 1] in clusters
    assert [2] in clusters
    assert len(clusters) == 2


def test_cluster_all_distinct_when_threshold_high() -> None:
    texts = ["alpha one", "beta two", "gamma three"]
    clusters = cluster_documents(texts, threshold=0.9)
    assert clusters == [[0], [1], [2]]


def test_cluster_empty_input() -> None:
    assert cluster_documents([]) == []
