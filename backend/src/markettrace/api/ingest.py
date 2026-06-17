"""Login-gated manual ingest endpoint.

``POST /ingest`` (auth required) kicks off ingestion in a FastAPI background
task and returns ``202 {"status": "started"}`` immediately. The work uses its
OWN DB session (the request session is closed once the response is sent) and is
idempotent: filings already present (matched on ``(source, external_id)``) are
skipped. It covers the two demo filings, a small validation corpus of recent
US 8-Ks (``_CORPUS_ISSUERS``), and the macro series (FRED). Each part is
isolated and persists incrementally, so a run cut short by the platform timeout
resumes on the next trigger.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select

from markettrace.api.auth import require_auth
from markettrace.config import get_settings
from markettrace.db.models import Document
from markettrace.db.session import make_engine, make_session_factory
from markettrace.pipeline.seed import (
    DEFAULT_WATCHLIST,
    KR_WATCHLIST,
    seed_instrument,
    seed_watchlist,
)
from markettrace.pipeline.vertical_slice import recompute_document_outcomes, run_slice
from markettrace.providers.registry import (
    get_disclosure_provider,
    get_price_provider,
)
from markettrace.storage.object_store import ObjectStore

__all__ = ["router", "run_demo_ingest"]

logger = logging.getLogger(__name__)

router = APIRouter()

# The demo filings ingested by POST /ingest (one US + one KR).
_DEMO_FILINGS: list[dict[str, str]] = [
    {
        "market": "US",
        "issuer_id": "320193",
        "ticker": "AAPL",
        "accession": "0000320193-26-000011",
        "market_index": "spy",
    },
    {
        "market": "KR",
        "issuer_id": "00126380",
        "ticker": "005930",
        "accession": "20260430800083",
        "market_index": None,  # resolved from settings below
    },
]

# Small validation corpus (blueprint phase 4): the most recent 8-Ks for a handful
# of US large caps, ingested by POST /ingest alongside the demo filings so the
# backtest/eval has more than two events to work with. 8-K = material-event
# report — short, event-dense, and cheap to extract (one gpt-4o-mini call each).
# CIKs verified against EDGAR. Idempotent: already-ingested filings are skipped
# (no LLM cost) and run_slice commits per filing, so a run cut short by the
# free-tier timeout resumes where it stopped on the next /ingest.
_CORPUS_FORMS = ("8-K",)
_CORPUS_PER_ISSUER = 10
_CORPUS_SINCE = datetime(2024, 1, 1, tzinfo=UTC)
_CORPUS_MARKET_INDEX = "spy"
_CORPUS_ISSUERS: list[dict[str, str]] = [
    {"ticker": "AAPL", "cik": "320193", "name": "Apple Inc.", "industry": "Technology"},
    {"ticker": "MSFT", "cik": "789019", "name": "Microsoft Corporation", "industry": "Technology"},
    {"ticker": "NVDA", "cik": "1045810", "name": "NVIDIA Corporation", "industry": "Technology"},
    {"ticker": "JPM", "cik": "19617", "name": "JPMorgan Chase & Co.", "industry": "Financials"},
    {"ticker": "XOM", "cik": "34088", "name": "Exxon Mobil Corporation", "industry": "Energy"},
]


def _ingest_one(session, store, settings, filing: dict[str, str]) -> None:
    """Resolve + run the vertical slice for a single demo filing (idempotent)."""
    market = filing["market"]
    ticker = filing["ticker"]
    accession = filing["accession"]

    if market == "US":
        disclosure = get_disclosure_provider("US", user_agent=settings.sec_user_agent)
        price = get_price_provider("US")
        market_index_ticker = filing["market_index"] or "spy"
    else:
        disclosure = get_disclosure_provider("KR")
        price = get_price_provider("KR")
        market_index_ticker = filing["market_index"] or settings.kr_market_index_ticker

    refs = disclosure.list_for_issuer(
        filing["issuer_id"],
        datetime(1970, 1, 1, tzinfo=UTC),
        primary_ticker=ticker,
    )
    ref = next((r for r in refs if r.external_id == accession), None)
    if ref is None:
        logger.warning(
            "ingest: filing %s not found for issuer %s (%s)",
            accession,
            filing["issuer_id"],
            market,
        )
        return

    existing = session.scalars(
        select(Document).where(
            Document.source == ref.source,
            Document.external_id == ref.external_id,
        )
    ).first()
    if existing is not None:
        # Already ingested: don't re-extract (no LLM cost, no duplicate events),
        # but recompute outcomes + event_impacts when they were produced by an
        # older engine (e.g. missing the 60-day horizon or the event_impacts the
        # /stats endpoint reads). Idempotent: a fully up-to-date doc recomputes 0.
        recomputed = recompute_document_outcomes(
            session,
            document=existing,
            price_provider=price,
            ticker=ticker,
            market=market,
            market_index_ticker=market_index_ticker,
        )
        if recomputed:
            logger.info(
                "ingest: recomputed outcomes for %d event(s) on existing %s/%s",
                recomputed,
                ref.source,
                ref.external_id,
            )
        else:
            logger.info(
                "ingest: existing document %s/%s already up to date; skipping",
                ref.source,
                ref.external_id,
            )
        return

    from markettrace.nlp.event_extractor import EventExtractor

    run_slice(
        session,
        store,
        ref=ref,
        disclosure_provider=disclosure,
        price_provider=price,
        extractor=EventExtractor(),
        ticker=ticker,
        market_index_ticker=market_index_ticker,
    )
    logger.info("ingest: completed %s/%s", ref.source, ref.external_id)


def _ingest_corpus(session, store, settings) -> None:
    """Ingest the most recent 8-Ks for each validation-corpus issuer (US).

    Seeds each issuer's Instrument, lists its recent 8-K filings, and runs the
    vertical slice on any not already ingested. Each filing is isolated in
    try/except and run_slice commits per filing, so one failure (or a timeout)
    leaves the successfully ingested filings persisted and the run resumable.
    """
    from markettrace.nlp.event_extractor import EventExtractor

    disclosure = get_disclosure_provider("US", user_agent=settings.sec_user_agent)
    price = get_price_provider("US")
    extractor = EventExtractor()

    for issuer in _CORPUS_ISSUERS:
        ticker = issuer["ticker"]
        seed_instrument(
            session,
            market="US",
            ticker=ticker,
            name=issuer["name"],
            industry=issuer.get("industry"),
        )
        session.commit()

        try:
            refs = disclosure.list_for_issuer(
                issuer["cik"],
                _CORPUS_SINCE,
                primary_ticker=ticker,
                forms=_CORPUS_FORMS,
            )
        except Exception:  # noqa: BLE001 - one issuer must not abort the rest
            session.rollback()
            logger.exception("corpus: listing failed for %s", ticker)
            continue

        ingested = 0
        for ref in refs[:_CORPUS_PER_ISSUER]:
            existing = session.scalars(
                select(Document).where(
                    Document.source == ref.source,
                    Document.external_id == ref.external_id,
                )
            ).first()
            if existing is not None:
                continue  # already ingested (idempotent) — cheap skip, no LLM call
            try:
                run_slice(
                    session,
                    store,
                    ref=ref,
                    disclosure_provider=disclosure,
                    price_provider=price,
                    extractor=extractor,
                    ticker=ticker,
                    market_index_ticker=_CORPUS_MARKET_INDEX,
                )
                ingested += 1
            except Exception:  # noqa: BLE001 - one filing must not abort the rest
                session.rollback()
                logger.exception(
                    "corpus: ingest failed for %s/%s", ref.source, ref.external_id
                )
        logger.info("corpus: %s ingested %d new 8-K(s)", ticker, ingested)


def _ingest_macro(session, settings) -> None:
    """Populate ``macro_observations`` from FRED (idempotent; needs FRED_API_KEY).

    Skipped with a log line when no key is configured so the rest of the demo
    ingest still succeeds. Wired here because production has no scheduled macro
    job — the admin's ``POST /ingest`` is the only trigger that runs in Render.
    """
    if settings.fred_api_key is None:
        logger.info("ingest: FRED_API_KEY not set; skipping macro ingest")
        return

    from markettrace.pipeline.macro_ingest import ingest_macro_series
    from markettrace.providers.registry import get_macro_provider

    provider = get_macro_provider("fred")
    inserted = ingest_macro_series(
        session,
        provider,
        settings.macro_series_list,
        now=datetime.now(UTC),
    )
    logger.info("ingest: macro inserted %s", inserted)


def run_demo_ingest() -> None:
    """Background worker: seed watchlists then ingest the demo filing set.

    Uses its own DB session. Each filing is wrapped in try/except so one failure
    does not abort the others.
    """
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session = make_session_factory(engine)()
    store = ObjectStore(settings.object_store_dir)
    try:
        seed_watchlist(session, DEFAULT_WATCHLIST)
        seed_watchlist(session, KR_WATCHLIST)
        session.commit()

        for filing in _DEMO_FILINGS:
            try:
                _ingest_one(session, store, settings, filing)
            except Exception:  # noqa: BLE001 - one filing must not abort the rest
                session.rollback()
                logger.exception("ingest: failed for %s/%s", filing["market"], filing["ticker"])

        try:
            _ingest_corpus(session, store, settings)
        except Exception:  # noqa: BLE001 - corpus failure must not abort the ingest
            session.rollback()
            logger.exception("ingest: corpus ingest failed")

        try:
            _ingest_macro(session, settings)
        except Exception:  # noqa: BLE001 - macro failure must not abort the ingest
            session.rollback()
            logger.exception("ingest: macro ingest failed")
    finally:
        session.close()


@router.post("/ingest", status_code=202)
def ingest(
    background_tasks: BackgroundTasks,
    _: None = Depends(require_auth),
) -> dict[str, str]:
    """Start the demo ingestion in the background; return immediately."""
    background_tasks.add_task(run_demo_ingest)
    return {"status": "started"}


def _ingest_summary(session) -> dict[str, object]:
    """Return current corpus counts: documents, events, and events per ticker."""
    from markettrace.db.models import Event, Instrument

    documents = session.scalar(select(func.count()).select_from(Document)) or 0
    events = session.scalar(select(func.count()).select_from(Event)) or 0
    rows = session.execute(
        select(Instrument.ticker, func.count(Event.id))
        .join(Event, Event.primary_instrument_id == Instrument.id)
        .group_by(Instrument.ticker)
        .order_by(func.count(Event.id).desc())
    ).all()
    return {
        "documents": documents,
        "events": events,
        "events_by_ticker": {ticker: count for ticker, count in rows},
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: run the full ingest (demo + corpus + macro) synchronously to completion.

    Unlike ``POST /ingest`` — which schedules a FastAPI ``BackgroundTask`` that a
    free-tier host may kill on idle spin-down before the corpus finishes — this
    runs the whole job in one foreground process, so it completes the corpus in a
    single invocation (e.g. a Render one-off job or shell). Idempotent: re-runs
    skip already-ingested filings cheaply. Honours ``DATABASE_URL`` from the
    environment, so point it at production by exporting that URL before running.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="markettrace-ingest", description=main.__doc__)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Skip ingest; just print current DB corpus counts.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.summary_only:
        run_demo_ingest()

    settings = get_settings()
    engine = make_engine(settings.database_url)
    session = make_session_factory(engine)()
    try:
        summary = _ingest_summary(session)
    finally:
        session.close()

    logger.info(
        "ingest summary: %d document(s), %d event(s)",
        summary["documents"],
        summary["events"],
    )
    for ticker, count in summary["events_by_ticker"].items():  # type: ignore[union-attr]
        logger.info("  %-8s %d event(s)", ticker, count)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
