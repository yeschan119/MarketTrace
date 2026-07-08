from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import polars as pl


@dataclass(frozen=True)
class DocumentRef:
    source: str
    external_id: str
    url: str
    market: str
    published_at: datetime
    title: str
    occurred_at: datetime | None = None
    primary_ticker: str | None = None


@dataclass(frozen=True)
class RawDocument:
    ref: DocumentRef
    content: str
    fetched_at: datetime
    content_bytes: bytes | None = None


@dataclass(frozen=True)
class IssuerResolution:
    """A market provider's canonical issuer id + primary ticker match."""

    issuer_id: str
    ticker: str
    name: str | None = None


@runtime_checkable
class DisclosureProvider(Protocol):
    market: str

    def list_recent(self, since: datetime) -> list[DocumentRef]: ...

    def list_for_issuer(
        self,
        issuer_id: str,
        since: datetime,
        *,
        primary_ticker: str | None = None,
    ) -> list[DocumentRef]: ...

    def fetch_raw(self, ref: DocumentRef) -> RawDocument: ...

    def resolve_issuer(self, query: str) -> IssuerResolution | None: ...


@runtime_checkable
class PriceProvider(Protocol):
    market: str

    def get_ohlcv(self, ticker: str, start: date, end: date) -> "pl.DataFrame": ...  # noqa: UP037


@dataclass(frozen=True)
class MacroPoint:
    """One vintage-preserving macroeconomic observation as first published.

    ``released_value`` is the value as it appeared on ``released_at`` (the
    initial release), not a later revision — this is what avoids look-ahead
    bias. ``previous_value`` is the prior period's released value when known.
    """

    series_id: str
    reference_date: date
    released_value: float
    released_at: datetime
    previous_value: float | None = None


@runtime_checkable
class MacroProvider(Protocol):
    source: str

    def get_observations(self, series_id: str, since: date) -> list[MacroPoint]: ...
