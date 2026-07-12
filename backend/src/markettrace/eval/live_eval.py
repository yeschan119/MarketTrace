"""Score the *deployed* extractor's stored event types against gold labels.

Unlike :mod:`markettrace.eval.harness` (which re-runs the live LLM extractor
over hand-written snippets and needs an API key), this measures the extractor
output that is *already in production*: a labelled sample of real events whose
``stored_event_type`` is the type the deployed model actually assigned. Scoring
it against a human-judged ``gold_family`` gives a live classification F1 with no
new model call — the offline half of the F1 story.

Both sides are normalised through :func:`~markettrace.eval.taxonomy.canonicalize`
so ``earnings_release``/``earnings_beat`` etc. are not counted as disagreements.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from markettrace.eval.metrics import (
    PRF,
    ClassificationReport,
    classification_metrics,
    entity_linking_metrics,
)
from markettrace.eval.taxonomy import canonicalize

__all__ = ["LiveEvalReport", "score_live_sample", "DEFAULT_LIVE_SAMPLE_PATH", "main"]

DEFAULT_LIVE_SAMPLE_PATH = (
    Path(__file__).resolve().parents[3] / "eval_data" / "live_sample.labeled.json"
)


@dataclass(frozen=True)
class LiveEvalReport:
    """Stored-output scores against human labels, plus mismatches."""

    classification: ClassificationReport
    n_examples: int
    # (event_id, stored_family, gold_family) for each disagreement.
    mismatches: list[tuple[int, str, str]]
    # Optional entity-linking score when the sample carries separate entity labels.
    entity_linking: PRF | None = None
    n_entity_examples: int = 0
    # (event_id, stored_entities, gold_entities) for entity-linking disagreements.
    entity_mismatches: list[tuple[int, set[str], set[str]]] | None = None


def _entity_values(rec: dict, keys: tuple[str, ...]) -> set[str] | None:
    for key in keys:
        if key not in rec:
            continue
        value = rec[key]
        if value is None:
            return set()
        if isinstance(value, str):
            return {value.upper()} if value else set()
        return {str(item).upper() for item in value if str(item)}
    return None


def score_live_sample(path: str | Path = DEFAULT_LIVE_SAMPLE_PATH) -> LiveEvalReport:
    """Load a labelled live sample and score stored event types against gold.

    The file is the object written by ``eval_data/live_sample.labeled.json``:
    a dict with an ``examples`` list of ``{event_id, stored_event_type,
    gold_family}`` records. Returns canonical-family P/R/F1 and the list of
    mismatches for inspection.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    examples = raw["examples"] if isinstance(raw, dict) else raw

    gold: list[str] = []
    pred: list[str] = []
    gold_links: dict[str, set[str]] = {}
    pred_links: dict[str, set[str]] = {}
    mismatches: list[tuple[int, str, str]] = []
    entity_mismatches: list[tuple[int, set[str], set[str]]] = []
    for rec in examples:
        event_id = int(rec["event_id"])
        stored_family = canonicalize(str(rec["stored_event_type"]))
        gold_family = canonicalize(str(rec["gold_family"]))
        pred.append(stored_family)
        gold.append(gold_family)
        if stored_family != gold_family:
            mismatches.append((event_id, stored_family, gold_family))

        gold_entities = _entity_values(rec, ("gold_entities", "gold_tickers", "gold_ticker"))
        stored_entities = _entity_values(
            rec,
            (
                "stored_entities",
                "stored_tickers",
                "stored_ticker",
                "predicted_entities",
                "predicted_tickers",
                "predicted_ticker",
            ),
        )
        if gold_entities is not None and stored_entities is not None:
            doc_id = str(event_id)
            gold_links[doc_id] = gold_entities
            pred_links[doc_id] = stored_entities
            if gold_entities != stored_entities:
                entity_mismatches.append((event_id, stored_entities, gold_entities))

    entity_report = (
        entity_linking_metrics(gold_links, pred_links) if gold_links or pred_links else None
    )

    return LiveEvalReport(
        classification=classification_metrics(gold, pred),
        n_examples=len(examples),
        mismatches=mismatches,
        entity_linking=entity_report,
        n_entity_examples=len(gold_links.keys() | pred_links.keys()),
        entity_mismatches=entity_mismatches if entity_report is not None else None,
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    """CLI entry point for ``markettrace-eval-live``: offline F1 of stored output."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="markettrace-eval-live",
        description="Score the deployed extractor's stored event types vs. gold labels.",
    )
    parser.add_argument("--sample", default=None, help="Path to a labelled live sample JSON.")
    args = parser.parse_args(argv)

    report = score_live_sample(args.sample) if args.sample else score_live_sample()
    payload = {
        "n_examples": report.n_examples,
        "canonical_macro_f1": report.classification.macro_f1,
        "canonical_accuracy": report.classification.accuracy,
        "n_mismatches": len(report.mismatches),
        "mismatches": [
            {"event_id": eid, "stored": s, "gold": g} for eid, s, g in report.mismatches
        ],
    }
    if report.entity_linking is None:
        payload["entity_linking"] = {
            "n_examples": 0,
            "status": "not_scored_no_entity_labels",
        }
    else:
        payload["entity_linking"] = {
            "n_examples": report.n_entity_examples,
            "precision": report.entity_linking.precision,
            "recall": report.entity_linking.recall,
            "f1": report.entity_linking.f1,
            "true_positives": report.entity_linking.true_positives,
            "false_positives": report.entity_linking.false_positives,
            "false_negatives": report.entity_linking.false_negatives,
            "mismatches": [
                {
                    "event_id": eid,
                    "stored": sorted(stored),
                    "gold": sorted(gold),
                }
                for eid, stored, gold in (report.entity_mismatches or [])
            ],
        }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
