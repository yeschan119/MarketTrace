"""Tests for the ticker-driven identifier resolvers (US CIK, KR corp_code).

No network access: httpx.MockTransport serves the SEC company_tickers.json and
the OpenDART corpCode.xml ZIP, both built in-memory.
"""

from __future__ import annotations

import io
import zipfile

import httpx

from markettrace.providers.opendart import OpenDartProvider
from markettrace.providers.sec_edgar import SecEdgarProvider

# ---------------------------------------------------------------------------
# SEC: ticker -> 10-digit CIK
# ---------------------------------------------------------------------------


_COMPANY_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corporation"},
    "2": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corporation"},
}


def _sec_provider() -> SecEdgarProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if "company_tickers" in str(request.url):
            return httpx.Response(200, json=_COMPANY_TICKERS)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": "t"})
    return SecEdgarProvider(user_agent="t", client=client)


def test_resolve_ciks_zero_pads_and_is_case_insensitive() -> None:
    out = _sec_provider().resolve_ciks(["aapl", "MSFT"])
    assert out == {"AAPL": "0000320193", "MSFT": "0000789019"}


def test_resolve_ciks_omits_unknown_tickers() -> None:
    out = _sec_provider().resolve_ciks(["AAPL", "ZZZZ"])
    assert out == {"AAPL": "0000320193"}
    assert "ZZZZ" not in out


def test_resolve_ciks_empty_request() -> None:
    assert _sec_provider().resolve_ciks([]) == {}


# ---------------------------------------------------------------------------
# OpenDART: stock_code -> 8-digit corp_code
# ---------------------------------------------------------------------------


def _corpcode_zip(rows: list[tuple[str, str, str]]) -> bytes:
    items = "".join(
        f"<list><corp_code>{c}</corp_code><corp_name>{n}</corp_name>"
        f"<stock_code>{s}</stock_code><modify_date>20240101</modify_date></list>"
        for c, n, s in rows
    )
    xml = f"<result>{items}</result>".encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return buf.getvalue()


def _kr_provider(rows: list[tuple[str, str, str]]) -> OpenDartProvider:
    zipped = _corpcode_zip(rows)

    def handler(request: httpx.Request) -> httpx.Response:
        if "corpCode" in str(request.url):
            return httpx.Response(200, content=zipped)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenDartProvider(api_key="k", client=client)


def test_resolve_corp_codes_maps_listed_companies() -> None:
    provider = _kr_provider(
        [
            ("00126380", "삼성전자", "005930"),
            ("00164779", "SK하이닉스", "000660"),
        ]
    )
    out = provider.resolve_corp_codes(["005930", "000660"])
    assert out == {"005930": "00126380", "000660": "00164779"}


def test_resolve_corp_codes_omits_non_listed_and_absent() -> None:
    provider = _kr_provider(
        [
            ("00126380", "삼성전자", "005930"),
            ("00999999", "비상장기업", " "),  # non-listed: blank stock_code
        ]
    )
    out = provider.resolve_corp_codes(["005930", "999999"])
    assert out == {"005930": "00126380"}


def test_resolve_corp_codes_empty_request() -> None:
    provider = _kr_provider([("00126380", "삼성전자", "005930")])
    assert provider.resolve_corp_codes([]) == {}
