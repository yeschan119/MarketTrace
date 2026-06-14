"""Pure precision / recall / F1 primitives.

No I/O, no model calls — just the arithmetic that turns predictions and gold
labels into classification (macro F1) and entity-linking (micro P/R/F1) scores.
This separation keeps the metrics unit-testable without an API key while the
:mod:`markettrace.eval.harness` glue runs the live extractor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "PRF",
    "prf_from_counts",
    "entity_linking_metrics",
    "ClassificationReport",
    "classification_metrics",
]


@dataclass(frozen=True)
class PRF:
    """Precision / recall / F1 with the underlying confusion counts."""

    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


def prf_from_counts(tp: int, fp: int, fn: int) -> PRF:
    """Build a :class:`PRF` from true/false positive/negative counts.

    Precision, recall, and F1 each default to ``0.0`` when their denominator is
    zero (the standard convention for an empty prediction or gold set).
    """
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return PRF(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
    )


def entity_linking_metrics(
    gold: Mapping[str, set[str]],
    predicted: Mapping[str, set[str]],
) -> PRF:
    """Micro-averaged P/R/F1 for entity linking across documents.

    *gold* and *predicted* map a document id to the set of linked entities
    (tickers) for that document. Counts are pooled across every document:

    - true positive: entity in both gold and predicted for the same document,
    - false positive: predicted but not in gold,
    - false negative: in gold but not predicted.

    Documents present in only one mapping are handled correctly (their entities
    count entirely as false negatives or false positives).
    """
    tp = fp = fn = 0
    for doc_id in gold.keys() | predicted.keys():
        g = gold.get(doc_id, set())
        p = predicted.get(doc_id, set())
        tp += len(g & p)
        fp += len(p - g)
        fn += len(g - p)
    return prf_from_counts(tp, fp, fn)


@dataclass(frozen=True)
class ClassificationReport:
    """Per-class P/R/F1 plus macro F1 and accuracy for a label set."""

    per_class: dict[str, PRF]
    macro_f1: float
    accuracy: float
    support: int


def classification_metrics(
    gold_labels: Sequence[str],
    predicted_labels: Sequence[str],
) -> ClassificationReport:
    """Compute a per-class report and macro F1 for single-label classification.

    *gold_labels* and *predicted_labels* must be equal-length parallel
    sequences. Macro F1 averages the per-class F1 over the union of labels seen
    in either sequence, weighting every class equally regardless of support.
    """
    if len(gold_labels) != len(predicted_labels):
        raise ValueError(
            "gold_labels and predicted_labels must be the same length "
            f"({len(gold_labels)} != {len(predicted_labels)})"
        )

    pairs = list(zip(gold_labels, predicted_labels, strict=True))
    labels = sorted(set(gold_labels) | set(predicted_labels))
    per_class: dict[str, PRF] = {}
    for label in labels:
        tp = sum(g == label and p == label for g, p in pairs)
        fp = sum(g != label and p == label for g, p in pairs)
        fn = sum(g == label and p != label for g, p in pairs)
        per_class[label] = prf_from_counts(tp, fp, fn)

    macro_f1 = (
        sum(prf.f1 for prf in per_class.values()) / len(per_class) if per_class else 0.0
    )
    correct = sum(g == p for g, p in pairs)
    support = len(gold_labels)
    accuracy = correct / support if support else 0.0

    return ClassificationReport(
        per_class=per_class,
        macro_f1=macro_f1,
        accuracy=accuracy,
        support=support,
    )
