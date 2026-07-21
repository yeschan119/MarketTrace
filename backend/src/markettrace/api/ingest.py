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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import func, select

from markettrace.api.auth import require_auth
from markettrace.api.schemas import InstrumentAnalyzeRequest, InstrumentAnalyzeResponse
from markettrace.config import get_settings
from markettrace.db.models import Document, Instrument
from markettrace.db.session import make_engine, make_session_factory
from markettrace.pipeline.price_refresh import DEFAULT_LOOKBACK_DAYS, refresh_recent_prices
from markettrace.pipeline.seed import (
    DEFAULT_WATCHLIST,
    KR_WATCHLIST,
    seed_instrument,
    seed_watchlist,
)
from markettrace.pipeline.vertical_slice import recompute_document_outcomes, run_slice
from markettrace.providers.base import IssuerResolution
from markettrace.providers.caching import CachingPriceProvider
from markettrace.providers.registry import (
    get_disclosure_provider,
    get_price_provider,
)
from markettrace.storage.object_store import ObjectStore

__all__ = ["router", "run_demo_ingest", "run_instrument_ingest"]

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

# US validation corpus: liquid large caps across sectors, driven by TICKER. CIKs
# are resolved from SEC's company_tickers.json at run time (no hand-curated CIKs
# to drift), so growing this list to the blueprint's 50-100 names is just adding
# tickers.
_CORPUS_US_ISSUERS: list[dict[str, str]] = [
    {"ticker": "AAPL", "name": "Apple Inc.", "industry": "Technology"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "industry": "Technology"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "industry": "Technology"},
    {"ticker": "AMZN", "name": "Amazon.com, Inc.", "industry": "Consumer Discretionary"},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "industry": "Communication Services"},
    {"ticker": "META", "name": "Meta Platforms, Inc.", "industry": "Communication Services"},
    {"ticker": "TSLA", "name": "Tesla, Inc.", "industry": "Consumer Discretionary"},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "industry": "Financials"},
    {"ticker": "XOM", "name": "Exxon Mobil Corporation", "industry": "Energy"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "industry": "Health Care"},
    {"ticker": "V", "name": "Visa Inc.", "industry": "Financials"},
    {"ticker": "WMT", "name": "Walmart Inc.", "industry": "Consumer Staples"},
    {"ticker": "UNH", "name": "UnitedHealth Group Incorporated", "industry": "Health Care"},
    {"ticker": "PG", "name": "The Procter & Gamble Company", "industry": "Consumer Staples"},
    {"ticker": "HD", "name": "The Home Depot, Inc.", "industry": "Consumer Discretionary"},
    {"ticker": "BAC", "name": "Bank of America Corporation", "industry": "Financials"},
    {"ticker": "KO", "name": "The Coca-Cola Company", "industry": "Consumer Staples"},
    {"ticker": "PFE", "name": "Pfizer Inc.", "industry": "Health Care"},
    {"ticker": "CVX", "name": "Chevron Corporation", "industry": "Energy"},
    {"ticker": "DIS", "name": "The Walt Disney Company", "industry": "Communication Services"},
]

# KR validation corpus: liquid KOSPI large caps, driven by 6-digit KRX TICKER.
# corp_codes are resolved from OpenDART corpCode.xml at run time. OpenDART has no
# form filter, so all recent filing types are listed and the extractor classifies
# them.
_CORPUS_KR_ISSUERS: list[dict[str, str]] = [
    {"ticker": "005930", "name": "Samsung Electronics Co., Ltd.", "industry": "Technology"},
    {"ticker": "000660", "name": "SK hynix Inc.", "industry": "Technology"},
    {"ticker": "373220", "name": "LG Energy Solution, Ltd.", "industry": "Industrials"},
    {"ticker": "207940", "name": "Samsung Biologics Co., Ltd.", "industry": "Health Care"},
    {"ticker": "005380", "name": "Hyundai Motor Company", "industry": "Consumer Discretionary"},
    {"ticker": "000270", "name": "Kia Corporation", "industry": "Consumer Discretionary"},
    {"ticker": "005490", "name": "POSCO Holdings Inc.", "industry": "Materials"},
    {"ticker": "035420", "name": "NAVER Corporation", "industry": "Communication Services"},
    {"ticker": "035720", "name": "Kakao Corp.", "industry": "Communication Services"},
    {"ticker": "051910", "name": "LG Chem, Ltd.", "industry": "Materials"},
    {"ticker": "006400", "name": "Samsung SDI Co., Ltd.", "industry": "Technology"},
    {"ticker": "028260", "name": "Samsung C&T Corporation", "industry": "Industrials"},
    {"ticker": "105560", "name": "KB Financial Group Inc.", "industry": "Financials"},
    {"ticker": "055550", "name": "Shinhan Financial Group Co., Ltd.", "industry": "Financials"},
    {"ticker": "012330", "name": "Hyundai Mobis Co., Ltd.", "industry": "Consumer Discretionary"},
    {"ticker": "068270", "name": "Celltrion, Inc.", "industry": "Health Care"},
    {"ticker": "015760", "name": "Korea Electric Power Corporation", "industry": "Utilities"},
    {"ticker": "032830", "name": "Samsung Life Insurance Co., Ltd.", "industry": "Financials"},
    {"ticker": "003670", "name": "POSCO Future M Co., Ltd.", "industry": "Materials"},
    {"ticker": "017670", "name": "SK Telecom Co., Ltd.", "industry": "Communication Services"},
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


def _ingest_issuer_filings(
    session,
    store,
    *,
    disclosure,
    price,
    extractor,
    market: str,
    issuer_id: str,
    ticker: str,
    name: str,
    industry: str | None,
    market_index_ticker: str,
    forms,
    limit: int | None = None,
) -> int:
    """Seed one corpus issuer and ingest its recent filings (idempotent).

    Lists the issuer's filings, caps at ``_CORPUS_PER_ISSUER``, skips any already
    in the DB (cheap, no LLM), and runs the vertical slice on the rest. Each
    filing is isolated in try/except and ``run_slice`` commits per filing, so one
    failure (or a platform timeout) leaves successful filings persisted and the
    run resumable. Returns the number of newly ingested filings.
    """
    seed_instrument(session, market=market, ticker=ticker, name=name, industry=industry)
    session.commit()

    try:
        refs = disclosure.list_for_issuer(
            issuer_id, _CORPUS_SINCE, primary_ticker=ticker, forms=forms
        )
    except TypeError:
        # Providers without a ``forms`` filter (OpenDART) take no such kwarg.
        refs = disclosure.list_for_issuer(issuer_id, _CORPUS_SINCE, primary_ticker=ticker)
    except Exception:  # noqa: BLE001 - one issuer must not abort the rest
        session.rollback()
        logger.exception("corpus: listing failed for %s", ticker)
        return 0

    cap = limit if limit is not None else _CORPUS_PER_ISSUER
    ingested = 0
    for ref in refs[:cap]:
        existing = session.scalars(
            select(Document).where(
                Document.source == ref.source,
                Document.external_id == ref.external_id,
            )
        ).first()
        if existing is not None:
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
                    "corpus: recomputed outcomes for %d event(s) on existing %s/%s",
                    recomputed,
                    ref.source,
                    ref.external_id,
                )
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
                market_index_ticker=market_index_ticker,
            )
            ingested += 1
        except Exception:  # noqa: BLE001 - one filing must not abort the rest
            session.rollback()
            logger.exception("corpus: ingest failed for %s/%s", ref.source, ref.external_id)
    logger.info("corpus: %s ingested %d new filing(s)", ticker, ingested)
    return ingested


def _normalize_ad_hoc_ticker(market: str, ticker: str) -> str:
    """Normalize user-entered ticker values for provider resolution."""
    ticker = ticker.strip().upper()
    if market == "KR" and ticker.isdigit() and len(ticker) < 6:
        return ticker.zfill(6)
    return ticker


def _resolve_ad_hoc_issuer(
    disclosure, request: InstrumentAnalyzeRequest
) -> IssuerResolution | None:
    """Resolve a user-entered ticker or company name to one provider issuer."""
    queries: list[str] = []
    if request.ticker:
        queries.append(_normalize_ad_hoc_ticker(request.market, request.ticker))
    if request.name and request.name not in queries:
        queries.append(request.name)

    for query in queries:
        resolution = disclosure.resolve_issuer(query)
        if resolution is not None:
            return resolution
    return None


def _build_ad_hoc_providers(settings, market: str):
    """Build disclosure/price providers and market-index config for ad hoc ingest."""
    if market == "US":
        return (
            get_disclosure_provider("US", user_agent=settings.sec_user_agent),
            CachingPriceProvider(get_price_provider("US")),
            _CORPUS_MARKET_INDEX,
            _CORPUS_FORMS,
        )

    if settings.opendart_api_key is None:
        return (None, None, None, None)

    return (
        get_disclosure_provider("KR"),
        CachingPriceProvider(get_price_provider("KR")),
        settings.kr_market_index_ticker,
        None,
    )


def _ingest_requested_instrument(
    session,
    store,
    settings,
    request: InstrumentAnalyzeRequest,
) -> int:
    """Resolve one requested issuer and run the vertical slice for recent filings.

    This powers the search-page "analyze this ticker" action. It deliberately
    drives providers by ticker, then reuses the same idempotent corpus ingestion
    primitive as the scheduled/manual corpus path.
    """
    from markettrace.nlp.event_extractor import EventExtractor

    market = request.market
    disclosure, price, market_index_ticker, forms = _build_ad_hoc_providers(settings, market)
    if disclosure is None or price is None or market_index_ticker is None:
        logger.warning("ad-hoc ingest: disclosure provider unavailable for %s", market)
        return 0

    resolution = _resolve_ad_hoc_issuer(disclosure, request)
    if resolution is None:
        logger.warning(
            "ad-hoc ingest: no issuer resolved for %s/%s",
            market,
            request.ticker or request.name,
        )
        return 0
    industry = request.industry

    return _ingest_issuer_filings(
        session,
        store,
        disclosure=disclosure,
        price=price,
        extractor=EventExtractor(),
        market=market,
        issuer_id=resolution.issuer_id,
        ticker=resolution.ticker,
        name=resolution.name or request.name or resolution.ticker,
        industry=industry,
        market_index_ticker=market_index_ticker,
        forms=forms,
        limit=request.max_filings,
    )


def run_instrument_ingest(request: InstrumentAnalyzeRequest) -> None:
    """Background worker for a single user-requested ticker analysis."""
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session = make_session_factory(engine)()
    store = ObjectStore(settings.object_store_dir)
    try:
        ingested = _ingest_requested_instrument(session, store, settings, request)
        logger.info(
            "ad-hoc ingest: completed %s/%s with %d new filing(s)",
            request.market,
            request.ticker,
            ingested,
        )
        try:
            from markettrace.impact.alerting import generate_watchlist_alerts

            created = generate_watchlist_alerts(session)
            if created:
                logger.info("ad-hoc ingest: generated %d watchlist alert(s)", created)
        except Exception:  # noqa: BLE001 - alerting must not abort the ingest
            session.rollback()
            logger.exception("ad-hoc ingest: watchlist alert generation failed")
    except Exception:  # noqa: BLE001 - background failures must be logged with context
        session.rollback()
        logger.exception(
            "ad-hoc ingest: failed for %s/%s", request.market, request.ticker
        )
    finally:
        session.close()


def _ingest_corpus_us(session, store, settings) -> None:
    """Ingest recent 8-Ks for the US validation corpus (CIKs resolved by ticker)."""
    from markettrace.nlp.event_extractor import EventExtractor

    disclosure = get_disclosure_provider("US", user_agent=settings.sec_user_agent)
    # Cache price fetches: the corpus re-requests each stock (overlapping windows)
    # and the market index (every filing) — without coalescing, the volume trips
    # Tiingo's free-tier 429 quota. Caching cuts ~1000 calls to ~one per ticker.
    price = CachingPriceProvider(get_price_provider("US"))
    extractor = EventExtractor()

    tickers = [i["ticker"] for i in _CORPUS_US_ISSUERS]
    try:
        ciks = disclosure.resolve_ciks(tickers)
    except Exception:  # noqa: BLE001 - resolution failure must not abort the ingest
        session.rollback()
        logger.exception("corpus: US CIK resolution failed")
        return

    for issuer in _CORPUS_US_ISSUERS:
        ticker = issuer["ticker"]
        cik = ciks.get(ticker.upper())
        if cik is None:
            logger.warning("corpus: no CIK for %s; skipping", ticker)
            continue
        _ingest_issuer_filings(
            session,
            store,
            disclosure=disclosure,
            price=price,
            extractor=extractor,
            market="US",
            issuer_id=cik,
            ticker=ticker,
            name=issuer["name"],
            industry=issuer.get("industry"),
            market_index_ticker=_CORPUS_MARKET_INDEX,
            forms=_CORPUS_FORMS,
        )


def _ingest_corpus_kr(session, store, settings) -> None:
    """Ingest recent filings for the KR validation corpus (corp_codes by ticker).

    Skipped when no OpenDART key is configured. corp_codes are resolved from
    OpenDART's corpCode.xml; OpenDART has no form filter so all recent filing
    types are listed and the extractor classifies them.
    """
    if settings.opendart_api_key is None:
        logger.info("ingest: OPENDART_API_KEY not set; skipping KR corpus")
        return

    from markettrace.nlp.event_extractor import EventExtractor

    disclosure = get_disclosure_provider("KR")
    price = CachingPriceProvider(get_price_provider("KR"))
    extractor = EventExtractor()
    market_index_ticker = settings.kr_market_index_ticker

    tickers = [i["ticker"] for i in _CORPUS_KR_ISSUERS]
    try:
        corp_codes = disclosure.resolve_corp_codes(tickers)
    except Exception:  # noqa: BLE001 - resolution failure must not abort the ingest
        session.rollback()
        logger.exception("corpus: KR corp_code resolution failed")
        return

    for issuer in _CORPUS_KR_ISSUERS:
        ticker = issuer["ticker"]
        corp_code = corp_codes.get(ticker)
        if corp_code is None:
            logger.warning("corpus: no corp_code for %s; skipping", ticker)
            continue
        _ingest_issuer_filings(
            session,
            store,
            disclosure=disclosure,
            price=price,
            extractor=extractor,
            market="KR",
            issuer_id=corp_code,
            ticker=ticker,
            name=issuer["name"],
            industry=issuer.get("industry"),
            market_index_ticker=market_index_ticker,
            forms=None,
        )


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


def _refresh_recent_prices(
    session,
    *,
    now: datetime,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[int, int]:
    """Refresh recent price bars for all tracked instruments.

    Recommendation and screener tabs read the ``prices`` table directly, while
    event/stat tabs read ``events`` and ``event_impacts``. Running this as part
    of the same daily ingest keeps the price freshness contract explicit instead
    of relying on whichever new filing happened to fetch a price window.
    """
    instruments = list(
        session.scalars(
            select(Instrument)
            .where(Instrument.delisted_at.is_(None))
            .order_by(Instrument.market.asc(), Instrument.ticker.asc())
        )
    )
    if not instruments:
        logger.info("ingest: no instruments found for recent price refresh")
        return {}

    provider_cache = {}

    def provider_for(market: str):
        provider = provider_cache.get(market)
        if provider is None:
            provider = get_price_provider(market)
            provider_cache[market] = provider
        return provider

    inserted = refresh_recent_prices(
        session,
        instruments,
        provider_for,
        now=now,
        lookback_days=lookback_days,
    )
    logger.info(
        "ingest: recent price refresh inserted %d row(s) across %d instrument(s)",
        sum(inserted.values()),
        len(inserted),
    )
    return inserted


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

        for corpus_ingest in (_ingest_corpus_us, _ingest_corpus_kr):
            try:
                corpus_ingest(session, store, settings)
            except Exception:  # noqa: BLE001 - corpus failure must not abort the ingest
                session.rollback()
                logger.exception("ingest: %s failed", corpus_ingest.__name__)

        try:
            _ingest_macro(session, settings)
        except Exception:  # noqa: BLE001 - macro failure must not abort the ingest
            session.rollback()
            logger.exception("ingest: macro ingest failed")

        try:
            _refresh_recent_prices(session, now=datetime.now(UTC))
        except Exception:  # noqa: BLE001 - price freshness must not abort the ingest
            session.rollback()
            logger.exception("ingest: recent price refresh failed")

        try:
            from markettrace.impact.alerting import generate_watchlist_alerts

            created = generate_watchlist_alerts(session)
            if created:
                logger.info("ingest: generated %d watchlist alert(s)", created)
        except Exception:  # noqa: BLE001 - alerting must not abort the ingest
            session.rollback()
            logger.exception("ingest: watchlist alert generation failed")
    finally:
        session.close()


@router.post("/ingest", status_code=202)
def ingest(
    background_tasks: BackgroundTasks,
    response: Response,
    wait: bool = False,
    _: None = Depends(require_auth),
) -> dict[str, object]:
    """Start the demo ingestion.

    Default mode preserves the web UI contract: schedule a background task and
    return immediately. ``?wait=true`` runs the same idempotent ingest in the
    request process and returns a summary after completion; this is intended for
    scheduled automation that must fail visibly when collection does not finish.
    """
    if wait:
        run_demo_ingest()
        response.status_code = 200
        return {"status": "completed", "summary": _load_ingest_summary()}

    background_tasks.add_task(run_demo_ingest)
    return {"status": "started"}


@router.post(
    "/instruments/analyze",
    status_code=202,
    response_model=InstrumentAnalyzeResponse,
)
def analyze_instrument(
    request: InstrumentAnalyzeRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_auth),
) -> InstrumentAnalyzeResponse:
    """Start ad hoc disclosure ingestion for one searched ticker.

    The request is auth-gated because it can spend provider quota and LLM calls.
    Work runs in the background; the Events page will show the new rows once the
    filings have been fetched, extracted, and scored.
    """
    if request.market == "KR" and get_settings().opendart_api_key is None:
        raise HTTPException(status_code=503, detail="OpenDART API key is not configured")
    settings = get_settings()
    disclosure, _, _, _ = _build_ad_hoc_providers(settings, request.market)
    if disclosure is None:
        raise HTTPException(status_code=503, detail="Disclosure provider is not configured")
    resolution = _resolve_ad_hoc_issuer(disclosure, request)
    if resolution is None:
        raise HTTPException(status_code=404, detail="No matching listed company found")

    normalized = request.model_copy(
        update={
            "ticker": resolution.ticker,
            "name": resolution.name or request.name,
        }
    )
    background_tasks.add_task(run_instrument_ingest, normalized)
    return InstrumentAnalyzeResponse(
        status="started",
        market=normalized.market,
        ticker=normalized.ticker,
        max_filings=normalized.max_filings,
    )


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


def _load_ingest_summary() -> dict[str, object]:
    """Open a short-lived session and return current ingest counts."""
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session = make_session_factory(engine)()
    try:
        return _ingest_summary(session)
    finally:
        session.close()


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

    summary = _load_ingest_summary()

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
