"""Multi-document grouping and novelty scoring.

The same underlying event is often reported by several documents (a company
press release, a regulator filing, a wire story). Counting each copy as an
independent signal double-counts the news, so this module:

1. Clusters near-duplicate texts via token Jaccard similarity
   (:func:`cluster_documents`), and
2. Scores how *novel* a candidate text is relative to texts already seen
   (:func:`novelty_score`) — ``1.0`` for a genuinely new story, decaying toward
   ``0.0`` for a rehash of something already on record.

Everything here is deterministic and dependency-free: identical inputs always
produce identical scores, preserving the system's reproducibility guarantee.
"""

from __future__ import annotations

import re

__all__ = ["tokenize", "jaccard_similarity", "novelty_score", "cluster_documents"]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set[str]:
    """Lowercase *text* and return the set of alphanumeric word tokens."""
    return set(_TOKEN_RE.findall(text.lower()))


def jaccard_similarity(a: str, b: str) -> float:
    """Token-set Jaccard similarity of two texts, in ``[0.0, 1.0]``.

    Two empty texts are defined as identical (``1.0``); an empty text against a
    non-empty one is fully dissimilar (``0.0``).
    """
    ta, tb = tokenize(a), tokenize(b)
    if not ta and not tb:
        return 1.0
    union = ta | tb
    if not union:
        return 0.0
    return len(ta & tb) / len(union)


def novelty_score(candidate: str, prior_texts: list[str]) -> float:
    """Return how novel *candidate* is versus *prior_texts*, in ``[0.0, 1.0]``.

    Defined as ``1.0 - max_similarity`` where ``max_similarity`` is the highest
    Jaccard similarity between *candidate* and any text in *prior_texts*. With no
    priors the candidate is fully novel (``1.0``); an exact rehash scores
    ``0.0``.
    """
    if not prior_texts:
        return 1.0
    max_sim = max(jaccard_similarity(candidate, prior) for prior in prior_texts)
    return 1.0 - max_sim


def cluster_documents(
    texts: list[str],
    *,
    threshold: float = 0.6,
) -> list[list[int]]:
    """Group *texts* into clusters of near-duplicates by Jaccard similarity.

    Single-link clustering: a text joins a cluster when it is at least
    *threshold* similar to **any** member already in that cluster. Returns a
    list of clusters, each a list of indices into *texts*, in first-seen order.
    Documents reporting the same event land in the same cluster so they can be
    collapsed into a single signal.
    """
    clusters: list[list[int]] = []
    for i, text in enumerate(texts):
        placed = False
        for cluster in clusters:
            if any(jaccard_similarity(text, texts[j]) >= threshold for j in cluster):
                cluster.append(i)
                placed = True
                break
        if not placed:
            clusters.append([i])
    return clusters
