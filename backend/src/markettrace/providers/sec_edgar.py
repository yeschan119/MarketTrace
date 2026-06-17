"""SEC EDGAR disclosure provider.

Fetches filing metadata from the EDGAR submissions API and raw document
content from the EDGAR archives.  Network access is fully injectable via
an ``httpx.Client`` so tests can supply a mock transport.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from markettrace.providers.base import DisclosureProvider, DocumentRef, RawDocument

if TYPE_CHECKING:
    pass

__all__ = ["SecEdgarProvider"]

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
# Authoritative ticker -> CIK map (one JSON file, refreshed by SEC nightly).
_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_ARCHIVE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{doc}"
)
# SEC fair-access: stay under 10 req/s and back off on throttling. EDGAR returns
# 429 (and occasionally 503) to bursty clients — datacenter IPs especially — so
# every request is spaced and retried with exponential backoff.
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_BACKOFF_BASE = 1.0
_RETRY_STATUS = frozenset({429, 503})


class SecEdgarProvider:
    """``DisclosureProvider`` backed by the SEC EDGAR submissions JSON API."""

    market: str = "US"

    def __init__(
        self,
        user_agent: str,
        client: httpx.Client | None = None,
        watchlist: list[tuple[str, str]] | None = None,
        *,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        min_request_interval: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
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
        max_retries:
            Times to retry a request that SEC throttles (429/503) before giving
            up and surfacing the error.
        backoff_base:
            Base seconds for exponential backoff (``base * 2**attempt``) used when
            the response carries no ``Retry-After`` header.
        min_request_interval:
            Minimum seconds between requests (a simple rate limiter). ``0`` (the
            default) disables spacing; production wires a small value to stay
            under SEC's 10 req/s limit.
        sleep / monotonic:
            Injectable clock/sleep so tests can exercise retry+backoff without
            real delays.
        """
        self._client = client or httpx.Client(headers={"User-Agent": user_agent})
        self._watchlist: list[tuple[str, str]] = watchlist or []
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._min_interval = min_request_interval
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    # ------------------------------------------------------------------
    # HTTP with rate limiting + retry on SEC throttling
    # ------------------------------------------------------------------

    def _get(self, url: str) -> httpx.Response:
        """GET *url*, spacing requests and retrying SEC throttle responses.

        Waits ``min_request_interval`` since the previous request, then retries
        429/503 up to ``max_retries`` times with backoff (honoring ``Retry-After``
        when present). The last response is returned even when still throttled, so
        the caller's ``raise_for_status`` surfaces a genuine, persistent failure.
        """
        resp: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            self._throttle()
            resp = self._client.get(url)
            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                self._sleep(self._retry_delay(resp, attempt))
                continue
            break
        assert resp is not None  # loop runs at least once
        return resp

    def _throttle(self) -> None:
        """Sleep so consecutive requests are at least ``min_request_interval`` apart."""
        if self._min_interval <= 0:
            return
        if self._last_request_at is not None:
            wait = self._min_interval - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        """Seconds to wait before a retry: ``Retry-After`` if given, else backoff."""
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass  # HTTP-date form (rare from SEC) — fall back to backoff
        return self._backoff_base * (2**attempt)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_for_cik(
        self,
        cik: str,
        since: datetime,
        *,
        primary_ticker: str | None = None,
        forms: Collection[str] | None = None,
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
        forms:
            If provided, only filings whose ``form`` is in this set are kept
            (e.g. ``{"8-K"}`` to restrict to material-event reports). Matching is
            exact on the EDGAR form code.
        """
        form_filter = set(forms) if forms else None

        url = _SUBMISSIONS_URL.format(cik=cik)
        resp = self._get(url)
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
            if form_filter is not None and form not in form_filter:
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
        forms: Collection[str] | None = None,
    ) -> list[DocumentRef]:
        """Market-agnostic alias for :meth:`list_for_cik`.

        ``issuer_id`` is the issuer's CIK for the US market.
        """
        return self.list_for_cik(
            issuer_id, since, primary_ticker=primary_ticker, forms=forms
        )

    def resolve_ciks(self, tickers: Collection[str]) -> dict[str, str]:
        """Map each ticker to its zero-padded 10-digit CIK via SEC's official file.

        Looks up ``company_tickers.json`` (the authoritative ticker->CIK map) so
        callers can drive ingestion by ticker without hand-curating CIKs. Matching
        is case-insensitive; tickers SEC does not list are omitted from the result.
        """
        wanted = {t.upper() for t in tickers}
        resp = self._get(_COMPANY_TICKERS_URL)
        resp.raise_for_status()
        out: dict[str, str] = {}
        for row in resp.json().values():
            ticker = str(row.get("ticker", "")).upper()
            if ticker in wanted and "cik_str" in row:
                out[ticker] = f"{int(row['cik_str']):010d}"
        return out

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
        resp = self._get(ref.url)
        resp.raise_for_status()
        return RawDocument(
            ref=ref,
            content=resp.text,
            fetched_at=datetime.now(UTC),
            content_bytes=resp.content,
        )


# Satisfy the Protocol at import-time (structural check).
_: DisclosureProvider = SecEdgarProvider.__new__(SecEdgarProvider)  # type: ignore[assignment]
