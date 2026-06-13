"""Login-gated manual ingest endpoint.

``POST /ingest`` (auth required) kicks off the demo ingestion set in a FastAPI
background task and returns ``202 {"status": "started"}`` immediately. The
background work uses its OWN DB session (the request session is closed once the
response is sent) and is idempotent: filings already present (matched on
``(source, external_id)``) are skipped.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select

from markettrace.api.auth import require_auth
from markettrace.config import get_settings
from markettrace.db.models import Document
from markettrace.db.session import make_engine, make_session_factory
from markettrace.pipeline.seed import (
    DEFAULT_WATCHLIST,
    KR_WATCHLIST,
    seed_watchlist,
)
from markettrace.pipeline.vertical_slice import run_slice
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
        logger.info("ingest: skipping existing document %s/%s", ref.source, ref.external_id)
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
