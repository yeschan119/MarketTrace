"""SEC EDGAR disclosure provider.

Fetches filing metadata from the EDGAR submissions API and raw document
content from the EDGAR archives.  Network access is fully injectable via
an ``httpx.Client`` so tests can supply a mock transport.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from markettrace.providers.base import (
    DisclosureProvider,
    DocumentRef,
    IssuerResolution,
    RawDocument,
)

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
# SEC refreshes company_tickers.json nightly and it is ~1MB / ~10k rows. The
# search box queries it per keystroke, so parsed rows are cached process-wide
# (providers are constructed per request) and only re-fetched twice a day.
_TICKER_CACHE_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class _CompanyRow:
    """One usable row of SEC's ticker->CIK map."""

    cik: str
    ticker: str
    name: str


# (fetched_at_monotonic, rows) — see _TICKER_CACHE_TTL_SECONDS.
_ticker_rows_cache: tuple[float, tuple[_CompanyRow, ...]] | None = None


def reset_company_row_cache() -> None:
    """Drop the cached ticker map. Exposed for tests."""
    global _ticker_rows_cache
    _ticker_rows_cache = None


def _normalize_company_query(value: str) -> str:
    """Normalize ticker/company-name lookup text for conservative matching."""
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _company_match_rank(query: str, ticker: str, name: str) -> tuple[int, int] | None:
    normalized_query = _normalize_company_query(query)
    normalized_ticker = _normalize_company_query(ticker)
    normalized_name = _normalize_company_query(name)
    if not normalized_query:
        return None
    if normalized_query == normalized_ticker:
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

    def _company_rows(self) -> tuple[_CompanyRow, ...]:
        """Return SEC's ticker->CIK map, cached process-wide for the TTL.

        Rows missing a ticker, name, or CIK are dropped so every caller can
        assume all three fields are present.
        """
        global _ticker_rows_cache
        # Deliberately the real clock, not the injectable ``_monotonic`` used for
        # request throttling: a test's frozen clock must not freeze this cache.
        now = time.monotonic()
        cached = _ticker_rows_cache
        if cached is not None and now - cached[0] < _TICKER_CACHE_TTL_SECONDS:
            return cached[1]

        resp = self._get(_COMPANY_TICKERS_URL)
        resp.raise_for_status()
        rows: list[_CompanyRow] = []
        for row in resp.json().values():
            ticker = str(row.get("ticker", "")).upper()
            name = str(row.get("title", "")).strip()
            if not ticker or not name or "cik_str" not in row:
                continue
            rows.append(
                _CompanyRow(cik=f"{int(row['cik_str']):010d}", ticker=ticker, name=name)
            )
        parsed = tuple(rows)
        _ticker_rows_cache = (now, parsed)
        return parsed

    def resolve_ciks(self, tickers: Collection[str]) -> dict[str, str]:
        """Map each ticker to its zero-padded 10-digit CIK via SEC's official file.

        Looks up ``company_tickers.json`` (the authoritative ticker->CIK map) so
        callers can drive ingestion by ticker without hand-curating CIKs. Matching
        is case-insensitive; tickers SEC does not list are omitted from the result.
        """
        wanted = {t.upper() for t in tickers}
        return {
            row.ticker: row.cik for row in self._company_rows() if row.ticker in wanted
        }

    def search_issuers(self, query: str, limit: int = 10) -> list[IssuerResolution]:
        """Return up to ``limit`` issuers matching a ticker or company-name query.

        Ordered best match first using the same ranking as
        :meth:`resolve_issuer`, which returns this list's head.
        """
        normalized_query = query.strip()
        if not normalized_query or limit < 1:
            return []

        ranked: list[tuple[tuple[int, int], IssuerResolution]] = []
        for row in self._company_rows():
            rank = _company_match_rank(normalized_query, row.ticker, row.name)
            if rank is None:
                continue
            ranked.append(
                (rank, IssuerResolution(issuer_id=row.cik, ticker=row.ticker, name=row.name))
            )
        # Stable sort on rank alone, so equally-ranked issuers keep registry
        # order and resolve_issuer picks the same one it always has.
        ranked.sort(key=lambda item: item[0])
        return [resolution for _, resolution in ranked[:limit]]

    def resolve_issuer(self, query: str) -> IssuerResolution | None:
        """Resolve a ticker or company-name query via SEC's official ticker map."""
        matches = self.search_issuers(query, limit=1)
        return matches[0] if matches else None

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
