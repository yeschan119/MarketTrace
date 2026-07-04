"""Re-extract events on already-ingested documents with the current extractor.

The deployed extractor prompt/taxonomy was improved after the corpus was first
ingested (live classification F1 77.3% -> 91.8%), but that improvement only
applies to *future* extractions — the events already in the DB still carry the
old classification. This module reapplies the current :class:`EventExtractor`
to documents already on record and updates each event's classification **in
place**:

* One document produced exactly one event (``run_slice`` never fans out), so the
  event is updated by id — ``outcomes``, UI deep-links, and review state survive.
* Numeric ``outcomes`` are classification-independent (returns don't move when a
  label changes), so they are left untouched.
* ``event_impacts`` fold ``event.direction`` into ``signed_abnormal_return``, so
  they are rebuilt from the existing outcomes whenever the event is updated.
* Human-reviewed events (``reviewed_at`` set) are skipped by default so manual
  corrections are never clobbered.

Raw text is read from the object store when the bytes are still present;
otherwise the disclosure is re-fetched from its provider. Production's object
store is ephemeral (``OBJECT_STORE_DIR=/tmp/...``), so re-fetch is the normal
path there — both providers reconstruct a fetch from the stored ``Document``
fields (SEC needs ``url``, OpenDART needs ``external_id``).

Dry-run is the default: the CLI reports what *would* change without persisting.
Pass ``--commit`` to write. Each event is isolated in its own try/commit so one
failure (or a platform timeout) leaves prior successes persisted and the run
resumable.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select

from markettrace.db.models import Document, Event, EventImpact, Instrument, ModelRun, Outcome
from markettrace.impact.event_impacts import build_event_impacts
from markettrace.impact.returns import OutcomeResult
from markettrace.providers.base import DocumentRef, RawDocument

__all__ = [
    "EventReextractResult",
    "ReextractReport",
    "reextract_event",
    "reextract_all",
    "main",
]

logger = logging.getLogger(__name__)

# Fields whose changes are worth surfacing in the dry-run diff. Numeric scores
# (confidence, surprise) also change but the classification triplet is what the
# taxonomy correction targets and what the signal stats depend on.
_DIFF_FIELDS = ("event_type", "direction")


@dataclass
class EventReextractResult:
    """Outcome of re-extracting a single event."""

    event_id: int
    status: str  # "updated" | "unchanged" | "skipped_reviewed" | "error"
    old_event_type: str | None = None
    new_event_type: str | None = None
    old_direction: str | None = None
    new_direction: str | None = None
    detail: str | None = None

    @property
    def changed(self) -> bool:
        return (
            self.old_event_type != self.new_event_type
            or self.old_direction != self.new_direction
        )


@dataclass
class ReextractReport:
    """Aggregate report for a re-extraction run."""

    dry_run: bool
    total: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_reviewed: int = 0
    errors: int = 0
    results: list[EventReextractResult] = field(default_factory=list)

    def record(self, result: EventReextractResult) -> None:
        self.total += 1
        self.results.append(result)
        if result.status == "updated":
            self.updated += 1
        elif result.status == "unchanged":
            self.unchanged += 1
        elif result.status == "skipped_reviewed":
            self.skipped_reviewed += 1
        elif result.status == "error":
            self.errors += 1


def _ref_from_document(document: Document) -> DocumentRef:
    """Reconstruct the minimal :class:`DocumentRef` a provider needs to re-fetch.

    ``fetch_raw`` only reads ``url`` (SEC) or ``external_id`` (OpenDART); the
    other fields are carried through for provenance and are populated from the
    stored row.
    """
    return DocumentRef(
        source=document.source,
        external_id=document.external_id,
        url=document.url,
        market=document.market,
        published_at=document.published_at,
        title=document.title or "",
        occurred_at=document.occurred_at,
    )


def _load_content(store, disclosure_provider, document: Document) -> str:
    """Return the raw text for *document*, preferring the object store.

    Reads the stored bytes when the object-store key is present and readable
    (cheap, no network, byte-identical to the original ingest); otherwise
    re-fetches from the provider. Raises on a fetch failure so the caller counts
    the event as an error rather than silently re-labelling on empty text.
    """
    if document.raw_object_key:
        try:
            return store.get(document.raw_object_key).decode("utf-8")
        except (FileNotFoundError, OSError, UnicodeDecodeError):
            logger.info(
                "reextract: object %s missing/unreadable for doc %s; re-fetching",
                document.raw_object_key,
                document.id,
            )

    raw: RawDocument = disclosure_provider.fetch_raw(_ref_from_document(document))
    return raw.content


def _outcome_results_for_event(session, event_id: int) -> list[OutcomeResult]:
    """Rebuild :class:`OutcomeResult` objects from an event's stored outcomes.

    Used to recompute ``event_impacts`` (which fold in ``direction``) without
    recomputing returns — the returns themselves don't depend on the label.
    """
    rows = session.scalars(
        select(Outcome).where(Outcome.event_id == event_id)
    ).all()
    return [
        OutcomeResult(
            horizon_days=o.horizon_days,
            raw_return=o.raw_return,
            market_return=o.market_return,
            abnormal_return=o.abnormal_return,
            sector_return=o.sector_return,
            sector_abnormal_return=o.sector_abnormal_return,
        )
        for o in rows
    ]


def reextract_event(
    session,
    store,
    *,
    event: Event,
    document: Document,
    instrument: Instrument | None,
    disclosure_provider,
    extractor,
    now: datetime,
    dry_run: bool,
) -> EventReextractResult:
    """Re-extract and (unless *dry_run*) persist one event's classification.

    Returns an :class:`EventReextractResult` describing the change. Does not
    commit — the caller owns the transaction boundary so it can isolate each
    event.
    """
    old_type = event.event_type
    old_direction = event.direction

    content = _load_content(store, disclosure_provider, document)
    extraction, model_version = extractor.extract(
        content, source_reliability=event.source_reliability
    )

    result = EventReextractResult(
        event_id=event.id,
        status="unchanged",
        old_event_type=old_type,
        new_event_type=extraction.event_type,
        old_direction=old_direction,
        new_direction=extraction.direction,
    )

    if dry_run:
        result.status = "updated" if result.changed else "unchanged"
        return result

    # Persist the new classification in place. novelty_score is intentionally
    # left as-is: it was computed against prior events at ingest time and
    # recomputing it here would depend on corpus iteration order.
    event.event_type = extraction.event_type
    event.entities = extraction.entities
    event.industries = extraction.industries
    event.channels = extraction.channels
    event.direction = extraction.direction
    event.horizon_days = extraction.horizon_days
    event.surprise_score = extraction.surprise_score
    if extraction.source_reliability is not None:
        event.source_reliability = extraction.source_reliability
    event.confidence = extraction.confidence
    event.evidence = extraction.evidence
    event.model = getattr(extractor, "model", None) or event.model
    event.model_version = model_version
    event.analyzed_at = now

    # Rebuild event_impacts from the (unchanged) outcomes: signed_abnormal_return
    # folds in the possibly-changed direction.
    session.execute(delete(EventImpact).where(EventImpact.event_id == event.id))
    outcomes = _outcome_results_for_event(session, event.id)
    industry = instrument.industry if instrument is not None else None
    for impact in build_event_impacts(event, outcomes, industry=industry, computed_at=now):
        session.add(impact)

    result.status = "updated" if result.changed else "unchanged"
    return result


def _disclosure_provider_for(market: str, settings, cache: dict):
    """Return (and memoise) a disclosure provider for *market*."""
    if market not in cache:
        from markettrace.providers.registry import get_disclosure_provider

        if market == "US":
            cache[market] = get_disclosure_provider(
                "US", user_agent=settings.sec_user_agent
            )
        else:
            cache[market] = get_disclosure_provider(market)
    return cache[market]


def reextract_all(
    session,
    store,
    *,
    settings,
    extractor=None,
    dry_run: bool = True,
    include_reviewed: bool = False,
    market: str | None = None,
    limit: int | None = None,
) -> ReextractReport:
    """Re-extract every event's classification with the current extractor.

    Iterates events joined to their document (and instrument), skipping
    human-reviewed events unless *include_reviewed*. Optionally filters by
    *market* and caps at *limit* events. Each event is isolated: on error the
    session is rolled back and the run continues; on success it commits per
    event so the work is resumable.
    """
    if extractor is None:
        from markettrace.nlp.event_extractor import EventExtractor

        extractor = EventExtractor()

    now = datetime.now(UTC)
    report = ReextractReport(dry_run=dry_run)
    provider_cache: dict = {}

    stmt = (
        select(Event, Document)
        .join(Document, Event.document_id == Document.id)
        .order_by(Event.id)
    )
    if market is not None:
        stmt = stmt.where(Document.market == market)
    if not include_reviewed:
        stmt = stmt.where(Event.reviewed_at.is_(None))
    if limit is not None:
        stmt = stmt.limit(limit)

    for event, document in session.execute(stmt).all():
        if event.reviewed_at is not None and not include_reviewed:
            # Belt-and-suspenders: the WHERE already excludes these.
            report.record(
                EventReextractResult(event_id=event.id, status="skipped_reviewed")
            )
            continue

        instrument = (
            session.get(Instrument, event.primary_instrument_id)
            if event.primary_instrument_id is not None
            else None
        )
        try:
            provider = _disclosure_provider_for(document.market, settings, provider_cache)
            result = reextract_event(
                session,
                store,
                event=event,
                document=document,
                instrument=instrument,
                disclosure_provider=provider,
                extractor=extractor,
                now=now,
                dry_run=dry_run,
            )
            if not dry_run:
                if result.status == "updated":
                    session.add(
                        ModelRun(
                            kind="reextract",
                            params={
                                "event_id": event.id,
                                "old_event_type": result.old_event_type,
                                "new_event_type": result.new_event_type,
                                "old_direction": result.old_direction,
                                "new_direction": result.new_direction,
                                "model_version": event.model_version,
                            },
                            data_version=None,
                            created_at=now,
                        )
                    )
                    session.commit()
                else:
                    # Nothing changed but the event fields were reassigned to
                    # identical values; commit so model_version/analyzed_at
                    # provenance reflects the re-run, then continue.
                    session.commit()
        except Exception as exc:  # noqa: BLE001 - one event must not abort the rest
            session.rollback()
            logger.exception("reextract: failed for event %s", event.id)
            report.record(
                EventReextractResult(
                    event_id=event.id, status="error", detail=str(exc)
                )
            )
            continue

        report.record(result)

    return report


def main(argv: list[str] | None = None) -> int:
    """CLI: re-extract stored events with the current extractor.

    Dry-run by default — prints the classification changes that *would* be made
    without writing. Pass ``--commit`` to persist. Honours ``DATABASE_URL`` and
    the LLM settings from the environment, so point it at production by exporting
    that URL (and the provider/API-key env) before running.
    """
    parser = argparse.ArgumentParser(
        prog="markettrace-reextract", description=main.__doc__
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persist changes. Without this flag the run is a dry run (default).",
    )
    parser.add_argument(
        "--market", default=None, help="Restrict to a single market (US or KR)."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap the number of events processed."
    )
    parser.add_argument(
        "--include-reviewed",
        action="store_true",
        help="Also re-extract human-reviewed events (clobbers manual corrections).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the full per-event report as JSON."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from markettrace.config import get_settings
    from markettrace.db.session import make_engine, make_session_factory
    from markettrace.storage.object_store import ObjectStore

    settings = get_settings()
    if settings.active_api_key is None:
        key_env = "OPENAI_API_KEY" if settings.llm_provider == "openai" else "ANTHROPIC_API_KEY"
        logger.error(
            "%s is not configured (LLM_PROVIDER=%s); cannot run extraction.",
            key_env,
            settings.llm_provider,
        )
        return 2

    engine = make_engine(settings.database_url)
    session = make_session_factory(engine)()
    store = ObjectStore(settings.object_store_dir)
    try:
        report = reextract_all(
            session,
            store,
            settings=settings,
            dry_run=not args.commit,
            include_reviewed=args.include_reviewed,
            market=args.market,
            limit=args.limit,
        )
    finally:
        session.close()

    mode = "DRY RUN (no changes written)" if report.dry_run else "COMMITTED"
    logger.info(
        "reextract %s: %d event(s) | %d changed | %d unchanged | %d skipped-reviewed | %d error",
        mode,
        report.total,
        report.updated,
        report.unchanged,
        report.skipped_reviewed,
        report.errors,
    )
    for r in report.results:
        if r.status == "updated" and r.changed:
            logger.info(
                "  event %s: %s/%s -> %s/%s",
                r.event_id,
                r.old_event_type,
                r.old_direction,
                r.new_event_type,
                r.new_direction,
            )

    if args.json:
        print(
            json.dumps(
                {
                    "dry_run": report.dry_run,
                    "total": report.total,
                    "updated": report.updated,
                    "unchanged": report.unchanged,
                    "skipped_reviewed": report.skipped_reviewed,
                    "errors": report.errors,
                    "results": [asdict(r) for r in report.results],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
