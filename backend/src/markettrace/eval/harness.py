"""Score event extraction against a gold set.

:func:`evaluate` is extractor-agnostic: it takes a ``predict`` callable so the
metrics path is fully testable with a stub. :func:`main` wires in the real
:class:`~markettrace.nlp.event_extractor.EventExtractor` for live runs (needs an
API key, like ``markettrace-slice``; not exercised in CI).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass

from markettrace.eval.goldset import GoldExample, load_goldset
from markettrace.eval.metrics import (
    PRF,
    ClassificationReport,
    classification_metrics,
    entity_linking_metrics,
)
from markettrace.eval.taxonomy import canonicalize

__all__ = ["Prediction", "EvalReport", "evaluate", "main"]


@dataclass(frozen=True)
class Prediction:
    """A single extractor prediction for one gold example."""

    event_type: str
    entities: set[str]


@dataclass(frozen=True)
class EvalReport:
    """Combined classification + entity-linking scores over a gold set.

    ``classification`` is scored at the *canonical family* level (the headline
    metric — see :mod:`markettrace.eval.taxonomy` for why raw strings are
    meaningless); ``raw_classification`` keeps the exact-string score for
    reference so the fragmentation gap is visible.
    """

    classification: ClassificationReport
    raw_classification: ClassificationReport
    entity_linking: PRF
    n_examples: int


def evaluate(
    goldset: list[GoldExample],
    predict: Callable[[GoldExample], Prediction],
) -> EvalReport:
    """Run *predict* over every gold example and score the predictions.

    Returns a :class:`EvalReport` bundling event-type macro F1 — both at the
    canonical-family level (headline) and raw-string level — and micro-averaged
    entity-linking P/R/F1. Event types are normalised with
    :func:`~markettrace.eval.taxonomy.canonicalize` before the headline score so
    ``earnings_release`` and ``earnings_beat`` are not counted as disagreements.
    Entity matching is case-insensitive (tickers upper-cased on both sides).
    """
    gold_raw: list[str] = []
    pred_raw: list[str] = []
    gold_canon: list[str] = []
    pred_canon: list[str] = []
    gold_links: dict[str, set[str]] = {}
    pred_links: dict[str, set[str]] = {}

    for example in goldset:
        prediction = predict(example)
        gold_raw.append(example.gold_event_type)
        pred_raw.append(prediction.event_type)
        gold_canon.append(canonicalize(example.gold_event_type))
        pred_canon.append(canonicalize(prediction.event_type))
        gold_links[example.id] = {e.upper() for e in example.gold_entities}
        pred_links[example.id] = {e.upper() for e in prediction.entities}

    return EvalReport(
        classification=classification_metrics(gold_canon, pred_canon),
        raw_classification=classification_metrics(gold_raw, pred_raw),
        entity_linking=entity_linking_metrics(gold_links, pred_links),
        n_examples=len(goldset),
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - live path
    """CLI entry point for ``markettrace-eval``: live extractor vs. gold set.

    Loads the bundled (or ``--goldset``-supplied) gold set, runs the real
    extractor over each example, and prints the report as JSON.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="markettrace-eval",
        description="Score the event extractor against a labelled gold set.",
    )
    parser.add_argument(
        "--goldset", default=None, help="Path to a gold set JSON file (default: bundled seed)."
    )
    args = parser.parse_args(argv)

    from markettrace.config import get_settings
    from markettrace.nlp.event_extractor import EventExtractor

    settings = get_settings()
    if settings.active_api_key is None:
        key_env = "OPENAI_API_KEY" if settings.llm_provider == "openai" else "ANTHROPIC_API_KEY"
        print(f"error: {key_env} is not configured; cannot run live eval.", file=sys.stderr)
        return 2

    goldset = load_goldset(args.goldset) if args.goldset else load_goldset()
    extractor = EventExtractor()

    def predict(example: GoldExample) -> Prediction:
        extraction, _ = extractor.extract(example.text)
        return Prediction(event_type=extraction.event_type, entities=set(extraction.entities))

    report = evaluate(goldset, predict)
    payload = {
        "n_examples": report.n_examples,
        "event_type_macro_f1": report.classification.macro_f1,
        "event_type_accuracy": report.classification.accuracy,
        "event_type_macro_f1_raw": report.raw_classification.macro_f1,
        "event_type_accuracy_raw": report.raw_classification.accuracy,
        "entity_linking": {
            "precision": report.entity_linking.precision,
            "recall": report.entity_linking.recall,
            "f1": report.entity_linking.f1,
        },
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
