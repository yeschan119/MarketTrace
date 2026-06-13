"""Tests for EventExtractor using a fully injected fake Anthropic client."""

from __future__ import annotations

import json
import types

import pytest

from markettrace.nlp.event_extractor import EventExtractor
from markettrace.nlp.schemas import (
    EVENT_TOOL_SCHEMA,
    EventExtraction,
    event_function_definition,
    event_tool_definition,
)

# ---------------------------------------------------------------------------
# Fake client helpers
# ---------------------------------------------------------------------------

def _make_tool_use_block(input_dict: dict) -> object:
    """Return a SimpleNamespace that looks like an Anthropic ToolUseBlock."""
    return types.SimpleNamespace(
        type="tool_use",
        name="record_event",
        input=input_dict,
    )


def _make_response(input_dict: dict, model: str = "claude-sonnet-4-6") -> object:
    """Return a fake Anthropic Message response."""
    return types.SimpleNamespace(
        content=[_make_tool_use_block(input_dict)],
        model=model,
        stop_reason="tool_use",
    )


class FakeMessages:
    """Fake client.messages namespace."""

    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):  # noqa: ARG002
        return self._response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


# ---------------------------------------------------------------------------
# Fake OpenAI client helpers
# ---------------------------------------------------------------------------

def _make_openai_response(input_dict: dict, model: str = "gpt-4o") -> object:
    """Return a fake OpenAI ChatCompletion with a forced function tool call."""
    tool_call = types.SimpleNamespace(
        function=types.SimpleNamespace(
            name="record_event",
            arguments=json.dumps(input_dict),
        )
    )
    message = types.SimpleNamespace(tool_calls=[tool_call], content=None)
    choice = types.SimpleNamespace(message=message, finish_reason="tool_calls")
    return types.SimpleNamespace(choices=[choice], model=model)


class FakeCompletions:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):  # noqa: ARG002
        return self._response


class FakeOpenAIClient:
    def __init__(self, response):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(response))


# ---------------------------------------------------------------------------
# Sample valid event payload
# ---------------------------------------------------------------------------

SAMPLE_EVENT_DICT = {
    "event_type": "earnings_beat",
    "entities": ["AAPL"],
    "industries": ["Technology"],
    "channels": ["earnings", "sentiment"],
    "direction": "positive",
    "horizon_days": 5,
    "surprise_score": 0.8,
    "novelty_score": None,
    "source_reliability": None,
    "confidence": 0.95,
    "evidence": [
        "Apple reported Q4 EPS of $1.46, beating the consensus estimate of $1.39.",
        "Revenue came in at $89.5B, above the $89.0B analyst expectation.",
    ],
}

MODEL_STRING = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Tests: EventExtractor.extract
# ---------------------------------------------------------------------------

class TestEventExtractor:
    def _extractor(self, payload: dict | None = None, model: str = MODEL_STRING) -> EventExtractor:
        response = _make_response(payload or SAMPLE_EVENT_DICT, model=model)
        client = FakeClient(response)
        return EventExtractor(client=client, model=model, provider="anthropic")

    def test_returns_validated_event_extraction(self):
        extractor = self._extractor()
        event, model_version = extractor.extract("Some document text.")

        assert isinstance(event, EventExtraction)
        assert event.event_type == "earnings_beat"
        assert event.direction == "positive"
        assert event.entities == ["AAPL"]
        assert event.confidence == pytest.approx(0.95)

    def test_returns_correct_model_version(self):
        extractor = self._extractor()
        _, model_version = extractor.extract("Some document text.")
        assert model_version == MODEL_STRING

    def test_backfills_source_reliability_when_model_omits_it(self):
        extractor = self._extractor()
        event, _ = extractor.extract("doc", source_reliability=0.9)
        assert event.source_reliability == pytest.approx(0.9)

    def test_does_not_overwrite_source_reliability_when_model_provided_it(self):
        payload = {**SAMPLE_EVENT_DICT, "source_reliability": 0.5}
        extractor = self._extractor(payload=payload)
        event, _ = extractor.extract("doc", source_reliability=0.9)
        # Model's value (0.5) must NOT be overwritten
        assert event.source_reliability == pytest.approx(0.5)

    def test_evidence_list_populated(self):
        extractor = self._extractor()
        event, _ = extractor.extract("doc")
        assert len(event.evidence) == 2
        assert "EPS" in event.evidence[0]

    def test_raises_on_missing_tool_use_block(self):
        """When the response has no tool_use block, extract() must raise ValueError."""
        bad_response = types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text="oops")],
            model=MODEL_STRING,
            stop_reason="end_turn",
        )
        client = FakeClient(bad_response)
        # Override FakeMessages to return the bad response
        client.messages = FakeMessages(bad_response)
        extractor = EventExtractor(client=client, model=MODEL_STRING, provider="anthropic")
        with pytest.raises(ValueError, match="No tool_use block"):
            extractor.extract("doc")


# ---------------------------------------------------------------------------
# Tests: EVENT_TOOL_SCHEMA
# ---------------------------------------------------------------------------

class TestEventToolSchema:
    def test_schema_type_is_object(self):
        assert EVENT_TOOL_SCHEMA["type"] == "object"

    def test_schema_has_properties(self):
        assert "properties" in EVENT_TOOL_SCHEMA

    def test_all_fields_present_in_properties(self):
        props = EVENT_TOOL_SCHEMA["properties"]
        expected_fields = {
            "event_type", "entities", "industries", "channels",
            "direction", "horizon_days", "surprise_score",
            "novelty_score", "source_reliability", "confidence", "evidence",
        }
        assert expected_fields <= set(props.keys())

    def test_required_includes_mandatory_fields(self):
        required = set(EVENT_TOOL_SCHEMA.get("required", []))
        assert "event_type" in required
        assert "direction" in required
        assert "confidence" in required

    def test_no_defs_or_schema_keys(self):
        """Anthropic-incompatible top-level keys must not be present."""
        assert "$defs" not in EVENT_TOOL_SCHEMA
        assert "$schema" not in EVENT_TOOL_SCHEMA

    def test_event_tool_definition_structure(self):
        defn = event_tool_definition()
        assert defn["name"] == "record_event"
        assert "description" in defn
        assert defn["input_schema"] is EVENT_TOOL_SCHEMA


# ---------------------------------------------------------------------------
# Tests: OpenAI provider path
# ---------------------------------------------------------------------------

class TestEventExtractorOpenAI:
    def _extractor(self, payload: dict | None = None, model: str = "gpt-4o") -> EventExtractor:
        response = _make_openai_response(payload or SAMPLE_EVENT_DICT, model=model)
        client = FakeOpenAIClient(response)
        return EventExtractor(client=client, model=model, provider="openai")

    def test_returns_validated_event_extraction(self):
        extractor = self._extractor()
        event, model_version = extractor.extract("Some document text.")

        assert isinstance(event, EventExtraction)
        assert event.event_type == "earnings_beat"
        assert event.direction == "positive"
        assert event.entities == ["AAPL"]
        assert model_version == "gpt-4o"

    def test_backfills_source_reliability_when_model_omits_it(self):
        extractor = self._extractor()
        event, _ = extractor.extract("doc", source_reliability=0.9)
        assert event.source_reliability == pytest.approx(0.9)

    def test_raises_on_missing_tool_call(self):
        message = types.SimpleNamespace(tool_calls=[], content="oops")
        choice = types.SimpleNamespace(message=message, finish_reason="stop")
        bad_response = types.SimpleNamespace(choices=[choice], model="gpt-4o")
        client = FakeOpenAIClient(bad_response)
        extractor = EventExtractor(client=client, model="gpt-4o", provider="openai")
        with pytest.raises(ValueError, match="No tool_calls"):
            extractor.extract("doc")


# ---------------------------------------------------------------------------
# Tests: event_function_definition (OpenAI format)
# ---------------------------------------------------------------------------

class TestEventFunctionDefinition:
    def test_function_definition_structure(self):
        defn = event_function_definition()
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "record_event"
        assert defn["function"]["parameters"] is EVENT_TOOL_SCHEMA
