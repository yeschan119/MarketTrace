"""OpenDART (DART/FSS) disclosure provider for the KR market.

Fetches filing metadata from the OpenDART ``list.json`` API and raw document
content (a ZIP of disclosure XML) from the ``document.xml`` endpoint. Network
access is fully injectable via an ``httpx.Client`` so tests can supply a mock
transport.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import httpx

from markettrace.providers.base import (
    DisclosureProvider,
    DocumentRef,
    IssuerResolution,
    RawDocument,
)

__all__ = ["OpenDartProvider"]

_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
_CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

# DART timestamps are Korea Standard Time (UTC+9).
_KST = timezone(timedelta(hours=9))

# corpCode.xml is a multi-megabyte ZIP that DART refreshes daily; see _corp_rows.
_CORPCODE_CACHE_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class _CorpRow:
    """One listed company from DART's corpCode registry."""

    corp_code: str
    stock_code: str
    corp_name: str


# (fetched_at_monotonic, rows) — see _CORPCODE_CACHE_TTL_SECONDS.
_corp_rows_cache: tuple[float, tuple[_CorpRow, ...]] | None = None


def reset_corp_row_cache() -> None:
    """Drop the cached corpCode registry. Exposed for tests."""
    global _corp_rows_cache
    _corp_rows_cache = None


def _normalize_company_query(value: str) -> str:
    """Normalize Korean/English issuer lookup text without losing Hangul."""
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _company_match_rank(query: str, ticker: str, name: str) -> tuple[int, int] | None:
    normalized_query = _normalize_company_query(query)
    normalized_ticker = _normalize_company_query(ticker)
    normalized_name = _normalize_company_query(name)
    if not normalized_query:
        return None
    if normalized_query == normalized_ticker:
        return (0, len(normalized_name))
    if normalized_query.isdigit() and normalized_ticker.endswith(normalized_query):
        return (0, len(normalized_name))
    if normalized_query == normalized_name:
        return (1, len(normalized_name))
    if normalized_name.startswith(normalized_query):
        return (2, len(normalized_name))
    if normalized_query in normalized_name:
        return (3, len(normalized_name))
    query_tokens = normalized_query.split()
    if query_tokens and all(token in normalized_name for token in query_tokens):
        return (4, len(normalized_name))
    return None


class OpenDartProvider:
    """``DisclosureProvider`` backed by the OpenDART (FSS) JSON/XML API."""

    market: str = "KR"

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        watchlist: list[tuple[str, str]] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        api_key:
            OpenDART API key (``crtfc_key`` query parameter).
        client:
            Optional injectable ``httpx.Client``; one is created when not given.
        watchlist:
            Optional list of ``(corp_code, stock_code)`` pairs used by
            ``list_recent``. ``corp_code`` is the 8-digit DART code; ``stock_code``
            is the 6-digit KRX ticker used as ``primary_ticker``.
        """
        self._client = client or httpx.Client()
        self._api_key = api_key
        self._watchlist: list[tuple[str, str]] = watchlist or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_for_corp(
        self,
        corp_code: str,
        since: datetime,
        *,
        primary_ticker: str | None = None,
    ) -> list[DocumentRef]:
        """Return ``DocumentRef`` objects for all filings since ``since``.

        Parameters
        ----------
        corp_code:
            The issuer's 8-digit DART ``corp_code``.
        since:
            Only filings with ``rcept_dt >= since.date()`` are returned.
        primary_ticker:
            If provided, attached to every ``DocumentRef`` as ``primary_ticker``.
            When ``None``, the row's own ``stock_code`` is used as a fallback.
        """
        resp = self._client.get(
            _LIST_URL,
            params={
                "crtfc_key": self._api_key,
                "corp_code": corp_code,
                "bgn_de": since.strftime("%Y%m%d"),
                "page_no": 1,
                "page_count": 100,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status")
        if status == "013":  # no data
            return []
        if status != "000":
            message = data.get("message", "")
            raise ValueError(f"OpenDART list error {status}: {message}")

        since_date = since.date()
        refs: list[DocumentRef] = []

        for item in data.get("list", []):
            rcept_dt = item.get("rcept_dt", "")
            filing_date = datetime.strptime(rcept_dt, "%Y%m%d").date()
            if filing_date < since_date:
                continue

            rcept_no = item["rcept_no"]
            stock_code = item.get("stock_code") or None
            ticker = primary_ticker if primary_ticker is not None else stock_code

            published_at = datetime(
                filing_date.year,
                filing_date.month,
                filing_date.day,
                tzinfo=_KST,
            )

            refs.append(
                DocumentRef(
                    source="opendart",
                    external_id=rcept_no,
                    url=_VIEWER_URL.format(rcept_no=rcept_no),
                    market="KR",
                    published_at=published_at,
                    title=item.get("report_nm", ""),
                    primary_ticker=ticker,
                )
            )

        return refs

    def list_for_issuer(
        self,
        issuer_id: str,
        since: datetime,
        *,
        primary_ticker: str | None = None,
    ) -> list[DocumentRef]:
        """Market-agnostic alias for :meth:`list_for_corp`.

        ``issuer_id`` is the issuer's 8-digit DART ``corp_code`` for the KR market.
        """
        return self.list_for_corp(issuer_id, since, primary_ticker=primary_ticker)

    def _corp_rows(self) -> tuple[_CorpRow, ...]:
        """Return listed companies from ``corpCode.xml``, cached for the TTL.

        OpenDART offers no ticker->corp_code lookup, so this downloads the
        ``corpCode.xml`` archive (a ZIP wrapping ``CORPCODE.xml``) and indexes the
        listed companies by ``stock_code``. The archive is multi-megabyte and the
        search box hits it per keystroke, so parsed rows are cached process-wide
        (providers are constructed per request). Entries without a stock code
        (non-listed entities) are dropped.
        """
        global _corp_rows_cache
        now = time.monotonic()
        cached = _corp_rows_cache
        if cached is not None and now - cached[0] < _CORPCODE_CACHE_TTL_SECONDS:
            return cached[1]

        resp = self._client.get(_CORPCODE_URL, params={"crtfc_key": self._api_key})
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
            xml_bytes = archive.read(archive.namelist()[0])
        root = ET.fromstring(xml_bytes)

        rows: list[_CorpRow] = []
        for item in root.iter("list"):
            stock_code = (item.findtext("stock_code") or "").strip()
            corp_code = (item.findtext("corp_code") or "").strip()
            corp_name = (item.findtext("corp_name") or "").strip()
            if not stock_code or not corp_code or not corp_name:
                continue
            rows.append(
                _CorpRow(corp_code=corp_code, stock_code=stock_code, corp_name=corp_name)
            )
        parsed = tuple(rows)
        _corp_rows_cache = (now, parsed)
        return parsed

    def resolve_corp_codes(self, stock_codes: Collection[str]) -> dict[str, str]:
        """Map each 6-digit KRX stock code to its 8-digit DART ``corp_code``.

        Lets callers drive KR ingestion by ticker instead of hand-curating
        corp_codes. Codes not present (e.g. a delisted or non-listed entity) are
        omitted from the result.
        """
        wanted = {s.strip() for s in stock_codes}
        return {
            row.stock_code: row.corp_code
            for row in self._corp_rows()
            if row.stock_code in wanted
        }

    def search_issuers(self, query: str, limit: int = 10) -> list[IssuerResolution]:
        """Return up to ``limit`` KR issuers matching a ticker or name query.

        Ordered best match first using the same ranking as
        :meth:`resolve_issuer`, which returns this list's head.
        """
        normalized_query = query.strip()
        if not normalized_query or limit < 1:
            return []

        ranked: list[tuple[tuple[int, int], IssuerResolution]] = []
        for row in self._corp_rows():
            rank = _company_match_rank(normalized_query, row.stock_code, row.corp_name)
            if rank is None:
                continue
            ranked.append(
                (
                    rank,
                    IssuerResolution(
                        issuer_id=row.corp_code,
                        ticker=row.stock_code,
                        name=row.corp_name,
                    ),
                )
            )
        # Stable sort on rank alone, so equally-ranked issuers keep registry
        # order and resolve_issuer picks the same one it always has.
        ranked.sort(key=lambda item: item[0])
        return [resolution for _, resolution in ranked[:limit]]

    def resolve_issuer(self, query: str) -> IssuerResolution | None:
        """Resolve a KRX ticker or Korean company-name query via corpCode.xml."""
        matches = self.search_issuers(query, limit=1)
        return matches[0] if matches else None

    def list_recent(self, since: datetime) -> list[DocumentRef]:
        """Return refs for all corps in the configured watchlist since ``since``.

        Returns an empty list when no watchlist was provided.
        """
        if not self._watchlist:
            return []

        refs: list[DocumentRef] = []
        for corp_code, stock_code in self._watchlist:
            refs.extend(
                self.list_for_corp(corp_code, since, primary_ticker=stock_code)
            )
        return refs

    def fetch_raw(self, ref: DocumentRef) -> RawDocument:
        """Fetch the raw disclosure XML for ``ref``.

        The ``document.xml`` endpoint returns a ZIP archive; the first ``.xml``
        entry is extracted and decoded (UTF-8 with an EUC-KR fallback).
        """
        resp = self._client.get(
            _DOCUMENT_URL,
            params={"crtfc_key": self._api_key, "rcept_no": ref.external_id},
        )
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
            xml_name = next(n for n in archive.namelist() if n.lower().endswith(".xml"))
            raw = archive.read(xml_name)

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("euc-kr")

        return RawDocument(
            ref=ref,
            content=content,
            fetched_at=datetime.now(UTC),
            content_bytes=resp.content,
        )


# Satisfy the Protocol at import-time (structural check).
_: DisclosureProvider = OpenDartProvider.__new__(OpenDartProvider)  # type: ignore[assignment]
