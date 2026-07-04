"""Tests for the corpus re-extraction pipeline.

In-memory SQLite + a temporary object store + fake extractor/provider. No
network or API key. Verifies: dry-run reports changes without mutating, commit
updates classification in place and rebuilds event_impacts, reviewed events are
protected, and the object-store/re-fetch content paths both work.
"""

from __future__ import annotations

from datetime import UTC, datetime

from markettrace.db.models import (
    Document,
    Event,
    EventImpact,
    Instrument,
    ModelRun,
    Outcome,
)
from markettrace.nlp.schemas import EventExtraction
from markettrace.pipeline.reextract import reextract_all
from markettrace.providers.base import RawDocument

_NOW = datetime(2024, 6, 1, tzinfo=UTC)
_PUBLISHED = datetime(2024, 5, 15, tzinfo=UTC)


class _FakeExtractor:
    """Returns a fixed extraction regardless of input text."""

    model = "fake-model-v2"

    def __init__(self, extraction: EventExtraction) -> None:
        self._extraction = extraction
        self.calls: list[str] = []

    def extract(self, text: str, *, source_reliability: float | None = None):
        self.calls.append(text)
        return self._extraction, "fake-model-v2-2024"


class _FakeProvider:
    """Disclosure provider that re-fetches fixed content (no object store)."""

    market = "US"

    def __init__(self, content: str = "re-fetched content") -> None:
        self._content = content
        self.fetches = 0

    def fetch_raw(self, ref) -> RawDocument:
        self.fetches += 1
        return RawDocument(ref=ref, content=self._content, fetched_at=_NOW)


class _Settings:
    sec_user_agent = "test agent"


def _new_extraction(event_type="earnings", direction="positive") -> EventExtraction:
    return EventExtraction(
        event_type=event_type,
        entities=["AAPL"],
        industries=["Technology"],
        channels=["sentiment"],
        direction=direction,
        horizon_days=5,
        confidence=0.8,
        evidence=["some verbatim sentence"],
    )


def _seed(session, store, *, content_in_store: bool, reviewed: bool = False):
    inst = Instrument(market="US", ticker="AAPL", name="Apple Inc.", industry="Technology")
    session.add(inst)
    session.flush()

    raw_key = store.put("original content") if content_in_store else None
    doc = Document(
        source="sec_edgar",
        external_id="0000320193-24-000123",
        url="https://www.sec.gov/x.htm",
        title="8-K",
        raw_object_key=raw_key,
        content_hash="hash-" + ("store" if content_in_store else "nostore"),
        market="US",
        published_at=_PUBLISHED,
        first_seen_at=_PUBLISHED,
    )
    session.add(doc)
    session.flush()

    event = Event(
        document_id=doc.id,
        primary_instrument_id=inst.id,
        event_type="macro",  # deliberately wrong old label
        entities=["AAPL"],
        industries=["Technology"],
        channels=["sentiment"],
        direction="negative",
        horizon_days=5,
        confidence=0.5,
        evidence=["old evidence"],
        model="old-model",
        model_version="old-model-2023",
        analyzed_at=_PUBLISHED,
        novelty_score=0.9,
        reviewed_at=_NOW if reviewed else None,
    )
    session.add(event)
    session.flush()

    # Two outcomes so event_impacts rebuild has rows to fold direction into.
    for horizon, ab in ((5, 0.04), (20, -0.02)):
        session.add(
            Outcome(
                event_id=event.id,
                instrument_id=inst.id,
                horizon_days=horizon,
                raw_return=ab + 0.01,
                market_return=0.01,
                abnormal_return=ab,
                computed_at=_PUBLISHED,
            )
        )
    # A stale impact row that must be rebuilt.
    session.add(
        EventImpact(
            event_id=event.id,
            instrument_id=inst.id,
            event_type="macro",
            industry="Technology",
            direction="negative",
            horizon_days=5,
            abnormal_return=0.04,
            signed_abnormal_return=-0.04,  # matches the OLD 'negative' direction
            computed_at=_PUBLISHED,
        )
    )
    session.commit()
    return doc, event, inst


class TestReextractDryRun:
    def test_dry_run_reports_change_without_mutating(self, db_session, tmp_object_store):
        doc, event, inst = _seed(db_session, tmp_object_store, content_in_store=True)
        extractor = _FakeExtractor(_new_extraction())

        report = reextract_all(
            db_session,
            tmp_object_store,
            settings=_Settings(),
            extractor=extractor,
            dry_run=True,
        )

        assert report.total == 1
        assert report.updated == 1
        assert report.results[0].old_event_type == "macro"
        assert report.results[0].new_event_type == "earnings"
        # Nothing persisted.
        db_session.expire_all()
        assert db_session.get(Event, event.id).event_type == "macro"
        assert db_session.get(Event, event.id).direction == "negative"


class TestReextractCommit:
    def test_commit_updates_event_and_rebuilds_impacts(self, db_session, tmp_object_store):
        doc, event, inst = _seed(db_session, tmp_object_store, content_in_store=True)
        extractor = _FakeExtractor(_new_extraction())

        report = reextract_all(
            db_session,
            tmp_object_store,
            settings=_Settings(),
            extractor=extractor,
            dry_run=False,
        )

        assert report.updated == 1
        db_session.expire_all()
        refreshed = db_session.get(Event, event.id)
        assert refreshed.event_type == "earnings"
        assert refreshed.direction == "positive"
        assert refreshed.model == "fake-model-v2"
        assert refreshed.model_version == "fake-model-v2-2024"
        # novelty_score preserved.
        assert refreshed.novelty_score == 0.9

        # event_impacts rebuilt: signed = abnormal * sign(positive) = +abnormal.
        rows = db_session.query(EventImpact).filter(EventImpact.event_id == event.id).all()
        signed = {r.horizon_days: r.signed_abnormal_return for r in rows}
        assert signed[5] == 0.04  # was -0.04 under the old 'negative' label
        assert signed[20] == -0.02

        # Outcomes untouched (returns are classification-independent).
        outcomes = db_session.query(Outcome).filter(Outcome.event_id == event.id).count()
        assert outcomes == 2

        # Provenance recorded.
        runs = db_session.query(ModelRun).filter(ModelRun.kind == "reextract").count()
        assert runs == 1

    def test_uses_object_store_and_avoids_refetch(self, db_session, tmp_object_store):
        _seed(db_session, tmp_object_store, content_in_store=True)
        extractor = _FakeExtractor(_new_extraction())
        provider = _FakeProvider()

        from markettrace.pipeline import reextract as mod

        # Inject our fake provider into the memoisation cache path.
        orig = mod._disclosure_provider_for
        mod._disclosure_provider_for = lambda market, settings, cache: provider
        try:
            reextract_all(
                db_session,
                tmp_object_store,
                settings=_Settings(),
                extractor=extractor,
                dry_run=False,
            )
        finally:
            mod._disclosure_provider_for = orig

        # Content came from the object store; the provider was never hit.
        assert provider.fetches == 0
        assert extractor.calls == ["original content"]

    def test_refetches_when_object_store_empty(self, db_session, tmp_object_store):
        _seed(db_session, tmp_object_store, content_in_store=False)
        extractor = _FakeExtractor(_new_extraction())
        provider = _FakeProvider(content="re-fetched content")

        from markettrace.pipeline import reextract as mod

        orig = mod._disclosure_provider_for
        mod._disclosure_provider_for = lambda market, settings, cache: provider
        try:
            reextract_all(
                db_session,
                tmp_object_store,
                settings=_Settings(),
                extractor=extractor,
                dry_run=False,
            )
        finally:
            mod._disclosure_provider_for = orig

        assert provider.fetches == 1
        assert extractor.calls == ["re-fetched content"]


class TestReextractReviewedProtection:
    def test_reviewed_event_skipped_by_default(self, db_session, tmp_object_store):
        doc, event, inst = _seed(
            db_session, tmp_object_store, content_in_store=True, reviewed=True
        )
        extractor = _FakeExtractor(_new_extraction())

        report = reextract_all(
            db_session,
            tmp_object_store,
            settings=_Settings(),
            extractor=extractor,
            dry_run=False,
        )

        # The reviewed event is excluded from the work set entirely.
        assert report.total == 0
        assert extractor.calls == []
        db_session.expire_all()
        assert db_session.get(Event, event.id).event_type == "macro"

    def test_include_reviewed_processes_it(self, db_session, tmp_object_store):
        doc, event, inst = _seed(
            db_session, tmp_object_store, content_in_store=True, reviewed=True
        )
        extractor = _FakeExtractor(_new_extraction())

        report = reextract_all(
            db_session,
            tmp_object_store,
            settings=_Settings(),
            extractor=extractor,
            dry_run=False,
            include_reviewed=True,
        )

        assert report.updated == 1
        db_session.expire_all()
        assert db_session.get(Event, event.id).event_type == "earnings"
