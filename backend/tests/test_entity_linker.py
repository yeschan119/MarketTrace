"""Tests for resolve_instrument and link_entities using in-memory SQLite."""

from __future__ import annotations

from datetime import UTC

import pytest

from markettrace.db.models import DocumentEntity, EntityAlias, Instrument
from markettrace.nlp.entity_linker import link_entities, resolve_instrument

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aapl(db_session):
    """Seed an AAPL Instrument and one alias."""
    instrument = Instrument(market="US", ticker="AAPL", name="Apple Inc.")
    db_session.add(instrument)
    db_session.flush()

    alias = EntityAlias(
        instrument_id=instrument.id,
        alias="apple",
        alias_type="common_name",
    )
    db_session.add(alias)
    db_session.flush()
    return instrument


@pytest.fixture
def fake_document(db_session, aapl):
    """A minimal stand-in for a Document row (we only need .id)."""
    # Use a SimpleNamespace so the test doesn't depend on Document's required columns.
    # link_entities only reads document.id.
    from datetime import datetime

    from markettrace.db.models import Document

    now = datetime.now(tz=UTC)
    doc = Document(
        source="test",
        external_id="doc-001",
        url="https://example.com/doc-001",
        content_hash="abc123",
        market="US",
        published_at=now,
        first_seen_at=now,
    )
    db_session.add(doc)
    db_session.flush()
    return doc


# ---------------------------------------------------------------------------
# resolve_instrument tests
# ---------------------------------------------------------------------------

class TestResolveInstrument:
    def test_resolves_by_ticker_exact(self, db_session, aapl):
        result = resolve_instrument(db_session, "AAPL")
        assert result is not None
        assert result.id == aapl.id

    def test_resolves_by_ticker_case_insensitive(self, db_session, aapl):
        result = resolve_instrument(db_session, "aapl")
        assert result is not None
        assert result.id == aapl.id

    def test_resolves_by_alias(self, db_session, aapl):
        result = resolve_instrument(db_session, "apple")
        assert result is not None
        assert result.id == aapl.id

    def test_resolves_by_alias_case_insensitive(self, db_session, aapl):
        result = resolve_instrument(db_session, "APPLE")
        assert result is not None
        assert result.id == aapl.id

    def test_returns_none_for_unknown(self, db_session, aapl):
        result = resolve_instrument(db_session, "MSFT")
        assert result is None

    def test_market_filter_matches(self, db_session, aapl):
        result = resolve_instrument(db_session, "AAPL", market="US")
        assert result is not None

    def test_market_filter_excludes(self, db_session, aapl):
        result = resolve_instrument(db_session, "AAPL", market="JP")
        assert result is None


# ---------------------------------------------------------------------------
# link_entities tests
# ---------------------------------------------------------------------------

class TestLinkEntities:
    def test_creates_document_entity_for_ticker(self, db_session, aapl, fake_document):
        entities = link_entities(db_session, fake_document, ["AAPL"])
        assert len(entities) == 1
        assert entities[0].instrument_id == aapl.id
        assert entities[0].document_id == fake_document.id
        assert entities[0].confidence == pytest.approx(1.0)

    def test_confidence_is_07_for_alias_match(self, db_session, aapl, fake_document):
        entities = link_entities(db_session, fake_document, ["apple"])
        assert len(entities) == 1
        assert entities[0].confidence == pytest.approx(0.7)

    def test_skips_unresolvable_tickers(self, db_session, aapl, fake_document):
        entities = link_entities(db_session, fake_document, ["MSFT", "GOOG"])
        assert entities == []

    def test_mixed_resolvable_and_not(self, db_session, aapl, fake_document):
        entities = link_entities(db_session, fake_document, ["AAPL", "MSFT"])
        assert len(entities) == 1
        assert entities[0].instrument_id == aapl.id

    def test_rows_flushed_to_session(self, db_session, aapl, fake_document):
        link_entities(db_session, fake_document, ["AAPL"])
        # After flush the row should be queryable within the same session
        row = db_session.get(DocumentEntity, 1)
        assert row is not None
        assert row.instrument_id == aapl.id

    def test_returns_empty_list_for_empty_tickers(self, db_session, aapl, fake_document):
        entities = link_entities(db_session, fake_document, [])
        assert entities == []
