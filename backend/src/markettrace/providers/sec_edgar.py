"""SEC EDGAR disclosure provider.

Fetches filing metadata from the EDGAR submissions API and raw document
content from the EDGAR archives.  Network access is fully injectable via
an ``httpx.Client`` so tests can supply a mock transport.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from markettrace.providers.base import DisclosureProvider, DocumentRef, RawDocument

if TYPE_CHECKING:
    pass

__all__ = ["SecEdgarProvider"]

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
_ARCHIVE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{doc}"
)


class SecEdgarProvider:
    """``DisclosureProvider`` backed by the SEC EDGAR submissions JSON API."""

    market: str = "US"

    def __init__(
        self,
        user_agent: str,
        client: httpx.Client | None = None,
        watchlist: list[tuple[str, str]] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        user_agent:
            Value for the ``User-Agent`` header (SEC requires a contact email).
        client:
            Optional injectable ``httpx.Client``; one is created when not given.
        watchlist:
            Optional list of ``(cik, ticker)`` pairs used by ``list_recent``.
        """
        self._client = client or httpx.Client(headers={"User-Agent": user_agent})
        self._watchlist: list[tuple[str, str]] = watchlist or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_for_cik(
        self,
        cik: str,
        since: datetime,
        *,
        primary_ticker: str | None = None,
    ) -> list[DocumentRef]:
        """Return ``DocumentRef`` objects for all filings since ``since``.

        Parameters
        ----------
        cik:
            The issuer's CIK (leading zeros are added automatically).
        since:
            Only filings with ``filingDate >= since.date()`` are returned.
        primary_ticker:
            If provided, attached to every ``DocumentRef`` as ``primary_ticker``.
        """
        url = _SUBMISSIONS_URL.format(cik=cik)
        resp = self._client.get(url)
        resp.raise_for_status()
        data = resp.json()

        recent = data.get("filings", {}).get("recent", {})
        forms: list[str] = recent.get("form", [])
        accessions: list[str] = recent.get("accessionNumber", [])
        filing_dates: list[str] = recent.get("filingDate", [])
        primary_docs: list[str] = recent.get("primaryDocument", [])
        primary_descs: list[str] = recent.get("primaryDocDescription", [])

        since_date = since.date()
        refs: list[DocumentRef] = []
        cik_int = int(cik)

        for form, accession, filing_date_str, primary_doc, desc in zip(
            forms, accessions, filing_dates, primary_docs, primary_descs, strict=False
        ):
            filing_date = datetime.fromisoformat(filing_date_str).date()
            if filing_date < since_date:
                continue

            accession_no_dashes = accession.replace("-", "")
            doc_url = _ARCHIVE_URL.format(
                cik_int=cik_int,
                accession=accession_no_dashes,
                doc=primary_doc,
            )

            published_at = datetime(
                filing_date.year,
                filing_date.month,
                filing_date.day,
                tzinfo=UTC,
            )

            refs.append(
                DocumentRef(
                    source="sec_edgar",
                    external_id=accession,
                    url=doc_url,
                    market="US",
                    published_at=published_at,
                    # primaryDocDescription is often empty; fall back to the form type
                    title=desc or form,
                    primary_ticker=primary_ticker,
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
        """Market-agnostic alias for :meth:`list_for_cik`.

        ``issuer_id`` is the issuer's CIK for the US market.
        """
        return self.list_for_cik(issuer_id, since, primary_ticker=primary_ticker)

    def list_recent(self, since: datetime) -> list[DocumentRef]:
        """Return refs for all CIKs in the configured watchlist since ``since``.

        Returns an empty list when no watchlist was provided.
        """
        if not self._watchlist:
            return []

        refs: list[DocumentRef] = []
        for cik, ticker in self._watchlist:
            refs.extend(
                self.list_for_cik(cik, since, primary_ticker=ticker)
            )
        return refs

    def fetch_raw(self, ref: DocumentRef) -> RawDocument:
        """Fetch the raw document bytes/text for ``ref``."""
        resp = self._client.get(ref.url)
        resp.raise_for_status()
        return RawDocument(
            ref=ref,
            content=resp.text,
            fetched_at=datetime.now(UTC),
            content_bytes=resp.content,
        )


# Satisfy the Protocol at import-time (structural check).
_: DisclosureProvider = SecEdgarProvider.__new__(SecEdgarProvider)  # type: ignore[assignment]
