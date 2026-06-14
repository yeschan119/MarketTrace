"""Load and validate the labelled evaluation gold set.

A gold set is a JSON array of examples, each pairing a disclosure snippet with
the event type and entities a correct extraction should produce. It is the
fixed reference the harness scores live extractor output against.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

__all__ = ["GoldExample", "load_goldset", "DEFAULT_GOLDSET_PATH"]

# Bundled seed gold set shipped with the package (small, hand-labelled).
DEFAULT_GOLDSET_PATH = Path(__file__).resolve().parents[3] / "eval_data" / "goldset.seed.json"


@dataclass(frozen=True)
class GoldExample:
    """One labelled evaluation example."""

    id: str
    text: str
    gold_event_type: str
    gold_entities: set[str]


def load_goldset(path: str | Path = DEFAULT_GOLDSET_PATH) -> list[GoldExample]:
    """Load and validate a gold set from *path*.

    Each record must contain ``id``, ``text``, ``gold_event_type`` and
    ``gold_entities`` (a list of ticker strings). Raises ``ValueError`` on a
    malformed record and ``FileNotFoundError`` if *path* does not exist.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("gold set must be a JSON array of example objects")

    examples: list[GoldExample] = []
    seen_ids: set[str] = set()
    for i, record in enumerate(raw):
        if not isinstance(record, dict):
            raise ValueError(f"gold set entry {i} is not an object")
        missing = {"id", "text", "gold_event_type", "gold_entities"} - record.keys()
        if missing:
            raise ValueError(f"gold set entry {i} is missing fields: {sorted(missing)}")

        example_id = str(record["id"])
        if example_id in seen_ids:
            raise ValueError(f"duplicate gold set id: {example_id!r}")
        seen_ids.add(example_id)

        entities = record["gold_entities"]
        if not isinstance(entities, list):
            raise ValueError(f"gold set entry {example_id!r}: gold_entities must be a list")

        examples.append(
            GoldExample(
                id=example_id,
                text=str(record["text"]),
                gold_event_type=str(record["gold_event_type"]),
                gold_entities={str(e) for e in entities},
            )
        )

    return examples
