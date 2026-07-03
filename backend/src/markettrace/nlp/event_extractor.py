"""LLM-powered market event extractor (Anthropic or OpenAI)."""

from __future__ import annotations

import json

from markettrace.nlp.schemas import (
    EVENT_TOOL_NAME,
    EventExtraction,
    event_function_definition,
    event_tool_definition,
)

_EXTRACTION_PROMPT = """\
You are a financial-event analyst. Your task is to read the document below and \
extract exactly ONE structured market event using the record_event tool.

Guidelines:
- event_type: a short snake_case label such as "earnings_beat", "product_launch", \
"regulatory_action", "merger_announcement", "macro_data_release", etc.
- entities: ticker symbols (preferred) or company/institution names mentioned as \
primary actors.
- industries: broad GICS sector names affected (e.g. "Technology", "Healthcare").
- channels: transmission mechanisms through which this event propagates to prices \
(e.g. "earnings", "sentiment", "supply_chain", "rates", "regulation").
- direction: "positive", "negative", or "neutral" — expected near-term price impact \
for the primary entities.
- horizon_days: the investment horizon in calendar days over which the impact is \
most likely to play out (e.g. 1 for intraday, 5 for a week, 90 for a quarter).
- surprise_score: 0-1 float capturing how unexpected the news is vs. consensus; \
omit (null) if the document gives no indication.
- novelty_score: 0-1 float capturing how unprecedented the event type is; \
omit (null) if unclear.
- source_reliability: omit (null) — will be filled from metadata when available.
- confidence: 0-1 reflecting how clearly the document supports your classification.
- evidence: 2-5 verbatim sentences from the document that most directly support \
your classification.

Do NOT output buy or sell recommendations.

--- DOCUMENT START ---
{text}
--- DOCUMENT END ---
"""


def _is_reasoning_model(model: str) -> bool:
    """True for OpenAI model families that reject the classic Chat Completions knobs.

    The GPT-5 line and the ``o`` reasoning series (o1/o3/o4) only accept the default
    temperature and require ``max_completion_tokens`` instead of ``max_tokens``;
    sending the old parameters returns a 400. Matched by name prefix so new point
    releases (e.g. ``gpt-5.4-mini``) are covered without a hardcoded allowlist.
    """
    m = model.lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


class EventExtractor:
    """Extract structured market events from text using an LLM tool call.

    Supports two providers, selected by ``provider`` (or ``settings.llm_provider``):

    - ``"anthropic"`` — the Anthropic Messages API (``client.messages.create``)
    - ``"openai"`` — the OpenAI Chat Completions API (``client.chat.completions.create``)

    Both use forced tool/function calling against the same :data:`EVENT_TOOL_SCHEMA`,
    so the validated :class:`EventExtraction` is identical regardless of provider.
    """

    def __init__(
        self,
        client=None,
        model: str | None = None,
        provider: str | None = None,
    ) -> None:
        self._client = client  # injected or lazily constructed
        self._model = model  # overrides settings.extraction_model when set
        self._provider = provider  # overrides settings.llm_provider when set

    @property
    def provider(self) -> str:
        """The resolved LLM provider for this extractor (``anthropic``/``openai``)."""
        return self._get_provider()

    @property
    def model(self) -> str:
        """The resolved model id this extractor will call."""
        return self._get_model()

    def _get_provider(self) -> str:
        if self._provider:
            return self._provider
        from markettrace.config import get_settings

        return get_settings().llm_provider

    def _get_client(self):
        if self._client is None:
            from markettrace.config import get_settings

            provider = self._get_provider()
            settings = get_settings()
            if provider == "openai":
                import openai

                self._client = openai.OpenAI(api_key=settings.openai_api_key)
            else:
                import anthropic

                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    def _get_model(self) -> str:
        if self._model:
            return self._model
        from markettrace.config import get_settings

        return get_settings().resolved_extraction_model

    def extract(
        self,
        text: str,
        *,
        source_reliability: float | None = None,
    ) -> tuple[EventExtraction, str]:
        """Extract a single market event from *text*.

        Parameters
        ----------
        text:
            Raw document text to analyse.
        source_reliability:
            Optional 0-1 reliability score for the document source.  When
            provided and the model omits the field, it is backfilled here.

        Returns
        -------
        (event, model_version)
            A validated :class:`EventExtraction` and the model string reported
            by the API.
        """
        client = self._get_client()
        model = self._get_model()
        prompt = _EXTRACTION_PROMPT.format(text=text)
        provider = self._get_provider()

        if provider == "openai":
            raw_input, model_version = self._call_openai(client, model, prompt)
        else:
            raw_input, model_version = self._call_anthropic(client, model, prompt)

        event = EventExtraction.model_validate(raw_input)

        # Backfill source_reliability if the caller supplied it and the model omitted it.
        if source_reliability is not None and event.source_reliability is None:
            event = event.model_copy(update={"source_reliability": source_reliability})

        return event, model_version

    @staticmethod
    def _call_anthropic(client, model: str, prompt: str) -> tuple[dict, str]:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0,
            tools=[event_tool_definition()],
            tool_choice={"type": "tool", "name": EVENT_TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        )

        # Locate the tool_use content block produced by forced tool_choice.
        tool_block = next(
            (block for block in response.content if getattr(block, "type", None) == "tool_use"),
            None,
        )
        if tool_block is None:
            raise ValueError(
                f"No tool_use block found in response. stop_reason={response.stop_reason!r}. "
                f"content={response.content!r}"
            )

        raw_input: dict = tool_block.input  # already a dict from the SDK
        return raw_input, response.model

    @staticmethod
    def _call_openai(client, model: str, prompt: str) -> tuple[dict, str]:
        request: dict = {
            "model": model,
            "tools": [event_function_definition()],
            "tool_choice": {"type": "function", "function": {"name": EVENT_TOOL_NAME}},
            "messages": [{"role": "user", "content": prompt}],
        }
        if _is_reasoning_model(model):
            # GPT-5 / o-series reasoning models reject the classic knobs: ``max_tokens``
            # is not accepted (use ``max_completion_tokens``) and only the default
            # temperature is allowed, so temperature is omitted entirely. The budget is
            # raised because hidden reasoning tokens draw from the same completion pool.
            request["max_completion_tokens"] = 4096
        else:
            request["max_tokens"] = 1024
            request["temperature"] = 0
        response = client.chat.completions.create(**request)

        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            raise ValueError(
                "No tool_calls found in response. "
                f"finish_reason={response.choices[0].finish_reason!r}. "
                f"content={message.content!r}"
            )

        # OpenAI returns function arguments as a JSON-encoded string.
        raw_input: dict = json.loads(tool_calls[0].function.arguments)
        return raw_input, response.model
