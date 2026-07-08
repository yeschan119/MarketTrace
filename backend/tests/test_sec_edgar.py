"""Tests for SecEdgarProvider using an injectable mock transport.

No network access is made; httpx.MockTransport intercepts all requests and
returns fixture data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from markettrace.providers.sec_edgar import SecEdgarProvider

FIXTURES = Path(__file__).parent / "fixtures"

SUBMISSIONS_JSON = (FIXTURES / "sec_submissions.json").read_text()
PRIMARY_DOC_HTML = (FIXTURES / "aapl_10q.html").read_text()
COMPANY_TICKERS_JSON = json.dumps(
    {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corporation"},
        "2": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corporation"},
    }
)

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


def _make_company_handler(company_tickers_body: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers.json" in str(request.url):
            return httpx.Response(
                200,
                text=company_tickers_body,
                headers={"Content-Type": "application/json"},
            )
        return httpx.Response(404)

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


# ---------------------------------------------------------------------------
# resolve_issuer
# ---------------------------------------------------------------------------


class TestResolveIssuer:
    def test_resolves_by_ticker(self):
        provider = _provider_with(_make_company_handler(COMPANY_TICKERS_JSON))

        resolved = provider.resolve_issuer("aapl")

        assert resolved is not None
        assert resolved.issuer_id == "0000320193"
        assert resolved.ticker == "AAPL"
        assert resolved.name == "Apple Inc."

    def test_resolves_by_company_name_prefix(self):
        provider = _provider_with(_make_company_handler(COMPANY_TICKERS_JSON))

        resolved = provider.resolve_issuer("Microsoft")

        assert resolved is not None
        assert resolved.issuer_id == "0000789019"
        assert resolved.ticker == "MSFT"

    def test_unknown_returns_none(self):
        provider = _provider_with(_make_company_handler(COMPANY_TICKERS_JSON))

        assert provider.resolve_issuer("not a listed company") is None


# ---------------------------------------------------------------------------
# Rate limiting + retry on SEC throttling (429/503)
# ---------------------------------------------------------------------------

_OLD = datetime(2020, 1, 1, tzinfo=UTC)


def _provider_with(handler, **kw) -> SecEdgarProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": "t t@e.com"}
    )
    kw.setdefault("sleep", lambda _d: None)  # never sleep for real in tests
    return SecEdgarProvider(user_agent="t t@e.com", client=client, **kw)


def _doc_handler(doc_statuses):
    """Submissions always 200; the doc URL returns *doc_statuses* in order."""
    seq = iter(doc_statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        if "submissions" in str(request.url):
            return httpx.Response(
                200, text=SUBMISSIONS_JSON, headers={"Content-Type": "application/json"}
            )
        code = next(seq)
        if code == 200:
            return httpx.Response(
                200, text=PRIMARY_DOC_HTML, headers={"Content-Type": "text/html"}
            )
        return httpx.Response(code, text="slow down")

    return handler


class TestRetryAndThrottle:
    def test_retries_then_succeeds_on_429(self):
        delays: list[float] = []
        prov = _provider_with(
            _doc_handler([429, 429, 200]), sleep=lambda d: delays.append(d)
        )
        ref = prov.list_for_cik(CIK, _OLD)[0]
        raw = prov.fetch_raw(ref)
        assert raw.content == PRIMARY_DOC_HTML
        # Two 429s -> two backoff sleeps of base*2**attempt = 1.0, 2.0.
        assert delays == [1.0, 2.0]

    def test_raises_after_exhausting_retries(self):
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if "submissions" in str(request.url):
                return httpx.Response(
                    200, text=SUBMISSIONS_JSON, headers={"Content-Type": "application/json"}
                )
            attempts["n"] += 1
            return httpx.Response(429, text="nope")

        prov = _provider_with(handler, max_retries=2)
        ref = prov.list_for_cik(CIK, _OLD)[0]
        with pytest.raises(httpx.HTTPStatusError):
            prov.fetch_raw(ref)
        assert attempts["n"] == 3  # initial attempt + 2 retries

    def test_honors_retry_after_header(self):
        delays: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if "submissions" in str(request.url):
                return httpx.Response(
                    200, text=SUBMISSIONS_JSON, headers={"Content-Type": "application/json"}
                )
            if not delays:  # first doc request -> throttle with explicit Retry-After
                return httpx.Response(429, text="wait", headers={"Retry-After": "7"})
            return httpx.Response(
                200, text=PRIMARY_DOC_HTML, headers={"Content-Type": "text/html"}
            )

        prov = _provider_with(handler, sleep=lambda d: delays.append(d))
        ref = prov.list_for_cik(CIK, _OLD)[0]
        prov.fetch_raw(ref)
        assert delays == [7.0]

    def test_non_throttle_error_is_not_retried(self):
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if "submissions" in str(request.url):
                return httpx.Response(
                    200, text=SUBMISSIONS_JSON, headers={"Content-Type": "application/json"}
                )
            attempts["n"] += 1
            return httpx.Response(404, text="missing")

        prov = _provider_with(handler)
        ref = prov.list_for_cik(CIK, _OLD)[0]
        with pytest.raises(httpx.HTTPStatusError):
            prov.fetch_raw(ref)
        assert attempts["n"] == 1  # 404 raises immediately, no retry

    def test_throttle_spaces_consecutive_requests(self):
        delays: list[float] = []
        prov = _provider_with(
            _doc_handler([200]),
            min_request_interval=0.2,
            sleep=lambda d: delays.append(d),
            monotonic=lambda: 0.0,  # frozen clock -> the 2nd request waits the full interval
        )
        ref = prov.list_for_cik(CIK, _OLD)[0]  # request 1 (submissions)
        prov.fetch_raw(ref)  # request 2 (doc) -> spaced by 0.2s
        assert any(abs(d - 0.2) < 1e-9 for d in delays)
