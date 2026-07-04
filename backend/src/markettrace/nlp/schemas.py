"""Pydantic schemas and provider tool definitions for event extraction.

The same JSON Schema (:data:`EVENT_TOOL_SCHEMA`) drives both the Anthropic tool
format (``input_schema``) and the OpenAI function-calling format (``parameters``).
"""

from __future__ import annotations

import copy
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from markettrace.nlp.taxonomy import CANONICAL_FAMILIES, canonicalize

# Sorted family list for a stable enum in the tool schema and the field docs.
_FAMILY_ENUM: list[str] = sorted(CANONICAL_FAMILIES)


class EventExtraction(BaseModel):
    """Structured market-event extracted from a document."""

    event_type: str = Field(
        description=(
            "Canonical snake_case category of the market event. MUST be exactly "
            "one of: " + ", ".join(_FAMILY_ENUM) + ". Use 'macro' only for "
            "macroeconomic indicator releases (never a single company's filing) "
            "and 'other' only when no family fits."
        )
    )

    @field_validator("event_type")
    @classmethod
    def _canonicalize_event_type(cls, v: str) -> str:
        """Collapse the value to a canonical family (belt-and-suspenders).

        The tool schema constrains the LLM to :data:`CANONICAL_FAMILIES` via an
        ``enum``, but that is a soft constraint — a model may still emit a
        near-synonym. Canonicalizing here guarantees every stored ``event_type``
        is one of the ~18 families, so the signal statistics never re-fragment.
        """
        return canonicalize(v)
    entities: list[str] = Field(description="Ticker symbols or company names involved.")
    industries: list[str] = Field(description="Industry sectors affected.")
    channels: list[str] = Field(
        description="Transmission channels, e.g. ['supply_chain', 'sentiment']."
    )
    direction: Literal["positive", "negative", "neutral"] = Field(
        description="Expected market impact direction."
    )
    horizon_days: int = Field(
        description="Investment horizon in calendar days over which the impact is expected."
    )
    surprise_score: float | None = Field(
        default=None,
        description="0-1 score of how surprising the event was vs consensus; null if unknown.",
    )
    novelty_score: float | None = Field(
        default=None,
        description="0-1 score of how novel/unprecedented the event is; null if unknown.",
    )
    source_reliability: float | None = Field(
        default=None,
        description="0-1 reliability score of the source; null if unknown.",
    )
    confidence: float = Field(
        description="0-1 model confidence in this extraction.",
    )
    evidence: list[str] = Field(
        description="Verbatim sentences from the document that support this event classification."
    )


def _build_tool_schema() -> dict:
    """Derive a clean Anthropic input_schema from EventExtraction's JSON schema.

    Anthropic requires a plain object schema with 'type', 'properties', and
    'required'. We strip top-level '$defs', '$schema', and 'title' keys that
    Pydantic emits but the API does not accept.
    """
    raw = EventExtraction.model_json_schema()
    schema: dict = copy.deepcopy(raw)

    # Remove keys incompatible with Anthropic tool input_schema
    for key in ("$defs", "$schema", "title"):
        schema.pop(key, None)

    # Strip 'title' from each property definition (Anthropic ignores it but
    # keeping it clean avoids any future validation issues).
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
        # anyOf wrapping for Optional fields — leave intact; the API handles it.

    # Constrain event_type to the canonical families at the API layer so the
    # model picks from the fixed enum instead of inventing near-synonyms. Both
    # Anthropic (input_schema) and OpenAI (parameters) honour a string ``enum``.
    event_type_prop = schema.get("properties", {}).get("event_type")
    if event_type_prop is not None:
        event_type_prop["enum"] = list(_FAMILY_ENUM)

    return schema


EVENT_TOOL_SCHEMA: dict = _build_tool_schema()

EVENT_TOOL_NAME = "record_event"
EVENT_TOOL_DESCRIPTION = (
    "Record a single structured market event extracted from the provided document. "
    "Populate every field carefully using only information present in the text. "
    "Use the evidence field to quote the verbatim sentences that justify each decision. "
    "Do NOT include investment advice or buy/sell recommendations."
)


def event_tool_definition() -> dict:
    """Return the Anthropic tool dict for the record_event tool."""
    return {
        "name": EVENT_TOOL_NAME,
        "description": EVENT_TOOL_DESCRIPTION,
        "input_schema": EVENT_TOOL_SCHEMA,
    }


def event_function_definition() -> dict:
    """Return the OpenAI function-calling tool dict for the record_event tool."""
    return {
        "type": "function",
        "function": {
            "name": EVENT_TOOL_NAME,
            "description": EVENT_TOOL_DESCRIPTION,
            "parameters": EVENT_TOOL_SCHEMA,
        },
    }
