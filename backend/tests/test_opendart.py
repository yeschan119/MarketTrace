"""Tests for OpenDartProvider using an injectable mock transport.

No network access is made; httpx.MockTransport intercepts all requests and
returns fixture data. The document.xml ZIP is built in-memory at runtime so
no binary blobs are committed to the fixtures directory.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from markettrace.providers.opendart import OpenDartProvider

FIXTURES = Path(__file__).parent / "fixtures"

LIST_JSON = (FIXTURES / "opendart_list.json").read_text()

CORP_CODE = "00126380"
PRIMARY_RCEPT_NO = "20240330000123"

_KST = timezone(timedelta(hours=9))

_XML_CONTENT = "<dart><company>삼성전자</company></dart>"
_CORP_CODE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list>
    <corp_code>00126380</corp_code>
    <corp_name>삼성전자</corp_name>
    <stock_code>005930</stock_code>
  </list>
  <list>
    <corp_code>00164779</corp_code>
    <corp_name>현대자동차</corp_name>
    <stock_code>005380</stock_code>
  </list>
</result>
"""

_STATUS_013_JSON = json.dumps({"status": "013", "message": "조회된 데이타가 없습니다."})
_STATUS_ERROR_JSON = json.dumps({"status": "010", "message": "미등록 인증키입니다."})


def _make_zip(xml_text: str) -> bytes:
    """Return in-memory ZIP bytes containing one UTF-8-encoded XML entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("document.xml", xml_text.encode("utf-8"))
    return buf.getvalue()


_ZIP_BYTES = _make_zip(_XML_CONTENT)
_CORP_CODE_ZIP_BYTES = _make_zip(_CORP_CODE_XML)


def _make_handler(list_body: str, zip_bytes: bytes):
    """Return an httpx handler that routes by endpoint path."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "list.json" in url:
            return httpx.Response(
                200, text=list_body, headers={"Content-Type": "application/json"}
            )
        if "document.xml" in url:
            return httpx.Response(
                200, content=zip_bytes, headers={"Content-Type": "application/zip"}
            )
        return httpx.Response(404)

    return handler


def _make_corp_code_handler(zip_bytes: bytes):
    def handler(request: httpx.Request) -> httpx.Response:
        if "corpCode.xml" in str(request.url):
            return httpx.Response(
                200, content=zip_bytes, headers={"Content-Type": "application/zip"}
            )
        return httpx.Response(404)

    return handler


@pytest.fixture
def provider() -> OpenDartProvider:
    transport = httpx.MockTransport(_make_handler(LIST_JSON, _ZIP_BYTES))
    client = httpx.Client(transport=transport)
    return OpenDartProvider(api_key="testkey", client=client)


# ---------------------------------------------------------------------------
# list_for_corp
# ---------------------------------------------------------------------------


class TestListForCorp:
    def test_returns_only_filings_on_or_after_since(self, provider: OpenDartProvider):
        # since = 2024-01-01 → two 2024 rows, the 2023 row is excluded
        since = datetime(2024, 1, 1, tzinfo=UTC)
        refs = provider.list_for_corp(CORP_CODE, since)
        assert len(refs) == 2

    def test_returns_all_when_since_is_old(self, provider: OpenDartProvider):
        since = datetime(2020, 1, 1, tzinfo=UTC)
        refs = provider.list_for_corp(CORP_CODE, since)
        assert len(refs) == 3

    def test_ref_url_contains_rcept_no(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        refs = provider.list_for_corp(CORP_CODE, since)
        assert len(refs) == 1
        assert f"rcpNo={PRIMARY_RCEPT_NO}" in refs[0].url

    def test_ref_published_at_is_kst(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        refs = provider.list_for_corp(CORP_CODE, since)
        ref = refs[0]
        assert ref.published_at.tzinfo is not None
        assert ref.published_at.utcoffset().total_seconds() == 9 * 3600
        assert ref.published_at == datetime(2024, 3, 30, tzinfo=_KST)

    def test_ref_title(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        refs = provider.list_for_corp(CORP_CODE, since)
        assert refs[0].title == "사업보고서"

    def test_ref_source_and_market(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        refs = provider.list_for_corp(CORP_CODE, since)
        ref = refs[0]
        assert ref.source == "opendart"
        assert ref.market == "KR"

    def test_primary_ticker_attached_when_provided(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        refs = provider.list_for_corp(CORP_CODE, since, primary_ticker="005930")
        assert refs[0].primary_ticker == "005930"

    def test_no_arg_falls_back_to_stock_code(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        refs = provider.list_for_corp(CORP_CODE, since)
        assert refs[0].primary_ticker == "005930"

    def test_status_013_returns_empty(self):
        transport = httpx.MockTransport(_make_handler(_STATUS_013_JSON, _ZIP_BYTES))
        client = httpx.Client(transport=transport)
        p = OpenDartProvider(api_key="testkey", client=client)
        refs = p.list_for_corp(CORP_CODE, datetime(2024, 1, 1, tzinfo=UTC))
        assert refs == []

    def test_status_error_raises_value_error(self):
        transport = httpx.MockTransport(_make_handler(_STATUS_ERROR_JSON, _ZIP_BYTES))
        client = httpx.Client(transport=transport)
        p = OpenDartProvider(api_key="testkey", client=client)
        with pytest.raises(ValueError, match="OpenDART list error 010"):
            p.list_for_corp(CORP_CODE, datetime(2024, 1, 1, tzinfo=UTC))


# ---------------------------------------------------------------------------
# list_recent
# ---------------------------------------------------------------------------


class TestListRecent:
    def test_empty_watchlist_returns_empty(self):
        transport = httpx.MockTransport(_make_handler(LIST_JSON, _ZIP_BYTES))
        client = httpx.Client(transport=transport)
        p = OpenDartProvider(api_key="testkey", client=client)
        refs = p.list_recent(datetime(2024, 1, 1, tzinfo=UTC))
        assert refs == []

    def test_watchlist_returns_refs_with_stock_code_as_ticker(self):
        transport = httpx.MockTransport(_make_handler(LIST_JSON, _ZIP_BYTES))
        client = httpx.Client(transport=transport)
        p = OpenDartProvider(
            api_key="testkey",
            client=client,
            watchlist=[(CORP_CODE, "005930")],
        )
        refs = p.list_recent(datetime(2024, 1, 1, tzinfo=UTC))
        assert len(refs) == 2
        assert all(r.primary_ticker == "005930" for r in refs)


# ---------------------------------------------------------------------------
# fetch_raw
# ---------------------------------------------------------------------------


class TestFetchRaw:
    def test_returns_raw_document_with_xml_content(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        ref = provider.list_for_corp(CORP_CODE, since)[0]
        raw = provider.fetch_raw(ref)
        assert raw.ref is ref
        assert "삼성전자" in raw.content

    def test_content_bytes_are_raw_zip_bytes(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        ref = provider.list_for_corp(CORP_CODE, since)[0]
        raw = provider.fetch_raw(ref)
        assert raw.content_bytes == _ZIP_BYTES
        assert len(raw.content_bytes) > 0

    def test_fetched_at_is_timezone_aware_utc(self, provider: OpenDartProvider):
        since = datetime(2024, 3, 1, tzinfo=UTC)
        ref = provider.list_for_corp(CORP_CODE, since)[0]
        raw = provider.fetch_raw(ref)
        assert raw.fetched_at.tzinfo is not None
        assert raw.fetched_at.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# list_for_issuer
# ---------------------------------------------------------------------------


class TestListForIssuer:
    def test_delegates_to_list_for_corp(self, provider: OpenDartProvider):
        since = datetime(2024, 1, 1, tzinfo=UTC)
        via_issuer = provider.list_for_issuer(CORP_CODE, since, primary_ticker="005930")
        via_corp = provider.list_for_corp(CORP_CODE, since, primary_ticker="005930")
        assert via_issuer == via_corp


# ---------------------------------------------------------------------------
# resolve_issuer
# ---------------------------------------------------------------------------


class TestResolveIssuer:
    def test_resolves_by_stock_code(self):
        transport = httpx.MockTransport(_make_corp_code_handler(_CORP_CODE_ZIP_BYTES))
        client = httpx.Client(transport=transport)
        provider = OpenDartProvider(api_key="testkey", client=client)

        resolved = provider.resolve_issuer("5930")

        assert resolved is not None
        assert resolved.issuer_id == "00126380"
        assert resolved.ticker == "005930"
        assert resolved.name == "삼성전자"

    def test_resolves_by_company_name(self):
        transport = httpx.MockTransport(_make_corp_code_handler(_CORP_CODE_ZIP_BYTES))
        client = httpx.Client(transport=transport)
        provider = OpenDartProvider(api_key="testkey", client=client)

        resolved = provider.resolve_issuer("현대자동차")

        assert resolved is not None
        assert resolved.issuer_id == "00164779"
        assert resolved.ticker == "005380"

    def test_unknown_returns_none(self):
        transport = httpx.MockTransport(_make_corp_code_handler(_CORP_CODE_ZIP_BYTES))
        client = httpx.Client(transport=transport)
        provider = OpenDartProvider(api_key="testkey", client=client)

        assert provider.resolve_issuer("없는회사") is None
