"""Parametrized contract test for the DisclosureProvider protocol (AC1).

This module is the executable expression of acceptance criterion AC1:
  Every DisclosureProvider implementation satisfies the same structural
  contract regardless of the underlying market (US/SEC-EDGAR, KR/OpenDART).

The assertion body is written once and exercised for both providers via
pytest parametrization. Adding a new market provider requires only
extending the ``_PROVIDERS`` fixture parameter list.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from markettrace.providers.base import DisclosureProvider, DocumentRef, RawDocument
from markettrace.providers.opendart import OpenDartProvider
from markettrace.providers.sec_edgar import SecEdgarProvider

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Provider factories (each builds a fully mocked provider + a since value)
# ---------------------------------------------------------------------------


def _make_us_provider() -> tuple[SecEdgarProvider, datetime]:
    submissions_json = (FIXTURES / "sec_submissions.json").read_text()
    doc_html = (FIXTURES / "aapl_10q.html").read_text()

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "submissions" in url:
            return httpx.Response(
                200, text=submissions_json, headers={"Content-Type": "application/json"}
            )
        return httpx.Response(200, text=doc_html, headers={"Content-Type": "text/html"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, headers={"User-Agent": "test test@example.com"})
    provider = SecEdgarProvider(
        user_agent="test test@example.com",
        client=client,
        watchlist=[("320193", "AAPL")],
    )
    return provider, datetime(2024, 1, 1, tzinfo=UTC)


def _make_kr_provider() -> tuple[OpenDartProvider, datetime]:
    list_json = (FIXTURES / "opendart_list.json").read_text()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("document.xml", "<dart><company>삼성전자</company></dart>")
    zip_bytes = buf.getvalue()

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "list.json" in url:
            return httpx.Response(
                200, text=list_json, headers={"Content-Type": "application/json"}
            )
        return httpx.Response(200, content=zip_bytes)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = OpenDartProvider(
        api_key="testkey",
        client=client,
        watchlist=[("00126380", "005930")],
    )
    return provider, datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture(params=["US", "KR"])
def provider_and_since(request):
    if request.param == "US":
        return _make_us_provider()
    return _make_kr_provider()


# ---------------------------------------------------------------------------
# Contract assertions — run against every parametrized provider
# ---------------------------------------------------------------------------


class TestDisclosureProviderContract:
    def test_satisfies_protocol(self, provider_and_since):
        provider, _ = provider_and_since
        assert isinstance(provider, DisclosureProvider)

    def test_market_is_nonempty_string(self, provider_and_since):
        provider, _ = provider_and_since
        assert isinstance(provider.market, str)
        assert provider.market != ""

    def test_list_recent_returns_list_of_document_refs(self, provider_and_since):
        provider, since = provider_and_since
        refs = provider.list_recent(since)
        assert isinstance(refs, list)
        assert len(refs) > 0
        assert all(isinstance(r, DocumentRef) for r in refs)

    def test_document_ref_required_fields_nonempty(self, provider_and_since):
        provider, since = provider_and_since
        refs = provider.list_recent(since)
        for ref in refs:
            assert ref.source != ""
            assert ref.external_id != ""
            assert ref.url != ""
            assert ref.market != ""

    def test_document_ref_market_matches_provider_market(self, provider_and_since):
        provider, since = provider_and_since
        refs = provider.list_recent(since)
        for ref in refs:
            assert ref.market == provider.market

    def test_document_ref_published_at_is_tz_aware(self, provider_and_since):
        provider, since = provider_and_since
        refs = provider.list_recent(since)
        for ref in refs:
            assert ref.published_at.tzinfo is not None

    def test_fetch_raw_returns_raw_document_bound_to_ref(self, provider_and_since):
        provider, since = provider_and_since
        ref = provider.list_recent(since)[0]
        raw = provider.fetch_raw(ref)
        assert isinstance(raw, RawDocument)
        assert raw.ref is ref

    def test_fetch_raw_content_is_nonempty_string(self, provider_and_since):
        provider, since = provider_and_since
        ref = provider.list_recent(since)[0]
        raw = provider.fetch_raw(ref)
        assert isinstance(raw.content, str)
        assert raw.content != ""

    def test_fetch_raw_fetched_at_is_utc(self, provider_and_since):
        provider, since = provider_and_since
        ref = provider.list_recent(since)[0]
        raw = provider.fetch_raw(ref)
        assert raw.fetched_at.tzinfo is not None
        assert raw.fetched_at.utcoffset().total_seconds() == 0
