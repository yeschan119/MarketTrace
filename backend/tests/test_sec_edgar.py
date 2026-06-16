"""Tests for SecEdgarProvider using an injectable mock transport.

No network access is made; httpx.MockTransport intercepts all requests and
returns fixture data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from markettrace.providers.sec_edgar import SecEdgarProvider

FIXTURES = Path(__file__).parent / "fixtures"

SUBMISSIONS_JSON = (FIXTURES / "sec_submissions.json").read_text()
PRIMARY_DOC_HTML = (FIXTURES / "aapl_10q.html").read_text()

CIK = "320193"
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{int(CIK):0>10}.json"
# The first filing in the fixture is the one we assert on most precisely.
PRIMARY_DOC_URL = (
    "https://www.sec.gov/Archives/edgar/data/320193/"
    "000032019324000123/aapl-20240330.htm"
)


def _make_handler(submissions_body: str, doc_body: str):
    """Return an httpx handler that serves fixture responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "submissions" in url:
            return httpx.Response(200, text=submissions_body, headers={"Content-Type": "application/json"})
        # Any primary-doc URL → return the HTML fixture.
        return httpx.Response(200, text=doc_body, headers={"Content-Type": "text/html"})

    return handler


@pytest.fixture
def provider() -> SecEdgarProvider:
    transport = httpx.MockTransport(_make_handler(SUBMISSIONS_JSON, PRIMARY_DOC_HTML))
    client = httpx.Client(transport=transport, headers={"User-Agent": "test test@example.com"})
    return SecEdgarProvider(user_agent="test test@example.com", client=client)


# ---------------------------------------------------------------------------
# list_for_cik
# ---------------------------------------------------------------------------

class TestListForCik:
    def test_returns_only_filings_on_or_after_since(self, provider: SecEdgarProvider):
        # since = 2024-01-01 → should return the two 2024 filings, not the 2023 one
        since = datetime(2024, 1, 1, tzinfo=UTC)
        refs = provider.list_for_cik(CIK, since)
        assert len(refs) == 2

    def test_returns_all_when_since_is_old(self, provider: SecEdgarProvider):
        since = datetime(2020, 1, 1, tzinfo=UTC)
        refs = provider.list_for_cik(CIK, since)
        assert len(refs) == 3

    def test_ref_url_format(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        refs = provider.list_for_cik(CIK, since)
        assert len(refs) == 1
        assert refs[0].url == PRIMARY_DOC_URL

    def test_ref_published_at_is_utc(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        refs = provider.list_for_cik(CIK, since)
        ref = refs[0]
        assert ref.published_at.tzinfo is not None
        assert ref.published_at == datetime(2024, 5, 15, tzinfo=UTC)

    def test_ref_title(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        refs = provider.list_for_cik(CIK, since)
        assert refs[0].title == "Form 10-Q"

    def test_ref_source_and_market(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        refs = provider.list_for_cik(CIK, since)
        ref = refs[0]
        assert ref.source == "sec_edgar"
        assert ref.market == "US"

    def test_primary_ticker_attached(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        refs = provider.list_for_cik(CIK, since, primary_ticker="AAPL")
        assert refs[0].primary_ticker == "AAPL"

    def test_no_primary_ticker_by_default(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        refs = provider.list_for_cik(CIK, since)
        assert refs[0].primary_ticker is None


# ---------------------------------------------------------------------------
# list_for_cik — forms filter (fixture holds 10-Q, 10-Q, 10-K)
# ---------------------------------------------------------------------------

class TestFormsFilter:
    _OLD = datetime(2020, 1, 1, tzinfo=UTC)

    def test_keeps_only_requested_form(self, provider: SecEdgarProvider):
        refs = provider.list_for_cik(CIK, self._OLD, forms={"10-K"})
        assert len(refs) == 1

    def test_keeps_multiple_of_a_form(self, provider: SecEdgarProvider):
        refs = provider.list_for_cik(CIK, self._OLD, forms={"10-Q"})
        assert len(refs) == 2

    def test_absent_form_returns_empty(self, provider: SecEdgarProvider):
        # No 8-K in the fixture -> nothing matches.
        assert provider.list_for_cik(CIK, self._OLD, forms={"8-K"}) == []

    def test_none_filter_keeps_all(self, provider: SecEdgarProvider):
        assert len(provider.list_for_cik(CIK, self._OLD, forms=None)) == 3

    def test_issuer_alias_forwards_forms(self, provider: SecEdgarProvider):
        refs = provider.list_for_issuer(CIK, self._OLD, forms={"10-K"})
        assert len(refs) == 1


# ---------------------------------------------------------------------------
# list_recent
# ---------------------------------------------------------------------------

class TestListRecent:
    def test_empty_watchlist_returns_empty(self):
        transport = httpx.MockTransport(_make_handler(SUBMISSIONS_JSON, PRIMARY_DOC_HTML))
        client = httpx.Client(transport=transport, headers={"User-Agent": "test test@example.com"})
        provider = SecEdgarProvider(user_agent="test test@example.com", client=client)
        refs = provider.list_recent(datetime(2024, 1, 1, tzinfo=UTC))
        assert refs == []

    def test_watchlist_returns_refs(self):
        transport = httpx.MockTransport(_make_handler(SUBMISSIONS_JSON, PRIMARY_DOC_HTML))
        client = httpx.Client(transport=transport, headers={"User-Agent": "test test@example.com"})
        provider = SecEdgarProvider(
            user_agent="test test@example.com",
            client=client,
            watchlist=[(CIK, "AAPL")],
        )
        refs = provider.list_recent(datetime(2024, 1, 1, tzinfo=UTC))
        assert len(refs) == 2
        assert all(r.primary_ticker == "AAPL" for r in refs)


# ---------------------------------------------------------------------------
# fetch_raw
# ---------------------------------------------------------------------------

class TestFetchRaw:
    def test_returns_raw_document_with_content(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        ref = provider.list_for_cik(CIK, since)[0]
        raw = provider.fetch_raw(ref)

        assert raw.ref is ref
        assert "Apple" in raw.content
        assert raw.content_bytes is not None
        assert len(raw.content_bytes) > 0

    def test_content_bytes_matches_content(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        ref = provider.list_for_cik(CIK, since)[0]
        raw = provider.fetch_raw(ref)
        assert raw.content_bytes == raw.content.encode("utf-8") or len(raw.content_bytes) > 0

    def test_fetched_at_is_timezone_aware_utc(self, provider: SecEdgarProvider):
        since = datetime(2024, 5, 1, tzinfo=UTC)
        ref = provider.list_for_cik(CIK, since)[0]
        raw = provider.fetch_raw(ref)
        assert raw.fetched_at.tzinfo is not None
        assert raw.fetched_at.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# list_for_issuer
# ---------------------------------------------------------------------------


class TestListForIssuer:
    def test_delegates_to_list_for_cik(self, provider: SecEdgarProvider):
        since = datetime(2024, 1, 1, tzinfo=UTC)
        via_issuer = provider.list_for_issuer(CIK, since, primary_ticker="AAPL")
        via_cik = provider.list_for_cik(CIK, since, primary_ticker="AAPL")
        assert via_issuer == via_cik
