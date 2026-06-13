"""OpenDART (DART/FSS) disclosure provider for the KR market.

Fetches filing metadata from the OpenDART ``list.json`` API and raw document
content (a ZIP of disclosure XML) from the ``document.xml`` endpoint. Network
access is fully injectable via an ``httpx.Client`` so tests can supply a mock
transport.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta, timezone

import httpx

from markettrace.providers.base import DisclosureProvider, DocumentRef, RawDocument

__all__ = ["OpenDartProvider"]

_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

# DART timestamps are Korea Standard Time (UTC+9).
_KST = timezone(timedelta(hours=9))


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
