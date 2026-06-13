"""Tests for the ingest layer.

Uses in-memory SQLite (via the ``db_session`` fixture) and a temporary
object store (``tmp_object_store``).  No network access.
"""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
from sqlalchemy import func
from sqlalchemy.orm import Session

from markettrace.db.models import Document, Instrument, Price
from markettrace.ingest.disclosures import ingest_document
from markettrace.ingest.prices import ingest_prices
from markettrace.providers.base import DocumentRef, RawDocument
from markettrace.storage.object_store import ObjectStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
_PUBLISHED = datetime(2024, 5, 15, tzinfo=UTC)


def _make_ref(external_id: str = "0000320193-24-000123") -> DocumentRef:
    return DocumentRef(
        source="sec_edgar",
        external_id=external_id,
        url=f"https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/{external_id}.htm",
        market="US",
        published_at=_PUBLISHED,
        title="Form 10-Q",
    )


def _make_raw(content: str = "<html>Apple 10-Q filing content.</html>", external_id: str = "0000320193-24-000123") -> RawDocument:
    ref = _make_ref(external_id)
    encoded = content.encode()
    return RawDocument(
        ref=ref,
        content=content,
        fetched_at=_NOW,
        content_bytes=encoded,
    )


def _make_instrument(session: Session) -> Instrument:
    inst = Instrument(market="US", ticker="AAPL", name="Apple Inc.")
    session.add(inst)
    session.flush()
    return inst


def _make_price_df(dates: list[str]) -> pl.DataFrame:
    n = len(dates)
    return pl.DataFrame(
        {
            "date": [
                pl.Series([d], dtype=pl.Utf8).str.to_date("%Y-%m-%d")[0]
                for d in dates
            ],
            "open": [150.0 + i for i in range(n)],
            "high": [155.0 + i for i in range(n)],
            "low": [148.0 + i for i in range(n)],
            "close": [153.0 + i for i in range(n)],
            "adj_close": [153.0 + i for i in range(n)],
            "volume": [50_000_000.0 + i * 1_000_000 for i in range(n)],
        }
    )


# ---------------------------------------------------------------------------
# ingest_document tests
# ---------------------------------------------------------------------------

class TestIngestDocument:
    def test_document_persisted(self, db_session: Session, tmp_object_store: ObjectStore):
        raw = _make_raw()
        doc = ingest_document(db_session, tmp_object_store, raw)

        assert doc.id is not None
        assert doc.source == "sec_edgar"
        assert doc.market == "US"
        assert doc.title == "Form 10-Q"

    def test_all_timestamps_non_null(self, db_session: Session, tmp_object_store: ObjectStore):
        raw = _make_raw()
        doc = ingest_document(db_session, tmp_object_store, raw)

        assert doc.published_at is not None
        assert doc.first_seen_at is not None
        # occurred_at is optional in the ref so may be None, but the other two must be set
        assert doc.published_at == _PUBLISHED
        assert doc.first_seen_at == _NOW

    def test_raw_object_key_set_and_content_retrievable(
        self, db_session: Session, tmp_object_store: ObjectStore
    ):
        raw = _make_raw()
        doc = ingest_document(db_session, tmp_object_store, raw)

        assert doc.raw_object_key is not None
        stored = tmp_object_store.get(doc.raw_object_key)
        assert stored == raw.content.encode()

    def test_content_hash_set(self, db_session: Session, tmp_object_store: ObjectStore):
        raw = _make_raw()
        doc = ingest_document(db_session, tmp_object_store, raw)
        expected_hash = tmp_object_store.hash_content(raw.content.encode())
        assert doc.content_hash == expected_hash

    def test_dedup_returns_same_document(self, db_session: Session, tmp_object_store: ObjectStore):
        raw = _make_raw()
        doc1 = ingest_document(db_session, tmp_object_store, raw)
        doc2 = ingest_document(db_session, tmp_object_store, raw)

        assert doc1.id == doc2.id

    def test_dedup_no_duplicate_row(self, db_session: Session, tmp_object_store: ObjectStore):
        raw = _make_raw()
        ingest_document(db_session, tmp_object_store, raw)
        ingest_document(db_session, tmp_object_store, raw)

        count = db_session.query(func.count(Document.id)).scalar()
        assert count == 1

    def test_different_content_creates_new_document(
        self, db_session: Session, tmp_object_store: ObjectStore
    ):
        raw1 = _make_raw(content="<html>filing A</html>", external_id="acc-001")
        raw2 = _make_raw(content="<html>filing B</html>", external_id="acc-002")
        doc1 = ingest_document(db_session, tmp_object_store, raw1)
        doc2 = ingest_document(db_session, tmp_object_store, raw2)

        assert doc1.id != doc2.id
        count = db_session.query(func.count(Document.id)).scalar()
        assert count == 2


# ---------------------------------------------------------------------------
# ingest_prices tests
# ---------------------------------------------------------------------------

class TestIngestPrices:
    def test_insert_new_rows(self, db_session: Session, tmp_object_store: ObjectStore):
        inst = _make_instrument(db_session)
        df = _make_price_df(["2024-01-02", "2024-01-03", "2024-01-04"])
        inserted = ingest_prices(db_session, inst.id, df)
        assert inserted == 3

    def test_prices_persisted_correctly(self, db_session: Session, tmp_object_store: ObjectStore):
        inst = _make_instrument(db_session)
        df = _make_price_df(["2024-01-02"])
        ingest_prices(db_session, inst.id, df)

        price = db_session.query(Price).filter_by(instrument_id=inst.id).first()
        assert price is not None
        assert price.open == 150.0
        assert price.close == 153.0
        assert price.adj_close == 153.0

    def test_reingest_overlapping_dates_no_duplicates(self, db_session: Session, tmp_object_store: ObjectStore):
        inst = _make_instrument(db_session)
        df1 = _make_price_df(["2024-01-02", "2024-01-03"])
        ingest_prices(db_session, inst.id, df1)

        # Overlap: 2024-01-03 already exists, 2024-01-04 is new
        df2 = _make_price_df(["2024-01-03", "2024-01-04"])
        inserted = ingest_prices(db_session, inst.id, df2)
        assert inserted == 1

        count = db_session.query(func.count(Price.id)).filter_by(instrument_id=inst.id).scalar()
        assert count == 3

    def test_fully_duplicate_frame_inserts_zero(self, db_session: Session, tmp_object_store: ObjectStore):
        inst = _make_instrument(db_session)
        df = _make_price_df(["2024-01-02", "2024-01-03"])
        ingest_prices(db_session, inst.id, df)
        inserted = ingest_prices(db_session, inst.id, df)
        assert inserted == 0

    def test_returns_inserted_count(self, db_session: Session, tmp_object_store: ObjectStore):
        inst = _make_instrument(db_session)
        df = _make_price_df(["2024-01-02", "2024-01-03", "2024-01-04"])
        count = ingest_prices(db_session, inst.id, df)
        assert count == 3
