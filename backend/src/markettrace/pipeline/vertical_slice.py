"""Vertical-slice pipeline: one disclosure -> event -> market-adjusted returns.

This module realizes the blueprint's "first vertical slice": fetch a single
disclosure, identify the company and structured event, persist the impact
hypothesis, and auto-compute market-adjusted returns at D+1/5/20.

It only *orchestrates* the already-implemented modules (providers, ingest,
nlp, impact); it does not reimplement any of their logic.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from markettrace.db.models import Event, EventImpact, Instrument, ModelRun, Outcome
from markettrace.impact.event_impacts import build_event_impacts
from markettrace.impact.returns import OutcomeResult, compute_event_outcomes
from markettrace.impact.sector_index import resolve_sector_index
from markettrace.ingest.disclosures import ingest_document
from markettrace.ingest.prices import ingest_prices
from markettrace.nlp.entity_linker import link_entities, resolve_instrument
from markettrace.nlp.novelty import novelty_score
from markettrace.providers.base import DocumentRef

__all__ = ["SliceResult", "run_slice", "recompute_document_outcomes", "main"]

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass
class SliceResult:
    """Identifiers and outcomes produced by a single pipeline run."""

    document_id: int
    event_id: int
    instrument_id: int
    outcomes: list[OutcomeResult]


def run_slice(
    session,
    store,
    *,
    ref: DocumentRef,
    disclosure_provider,
    price_provider,
    extractor,
    ticker: str,
    market_index_ticker: str = "spy",
    sector_index_ticker: str | None = None,
    horizons: tuple[int, ...] = (1, 5, 20, 60),
) -> SliceResult:
    """Run the end-to-end vertical slice for a single disclosure ``ref``.

    Steps:
    a. Fetch and ingest the raw disclosure (dedup on content hash).
    b. Resolve the primary instrument and link entities.
    c. Extract a structured event from the disclosure text.
    d. Persist the event (impact hypothesis).
    e. Fetch a price window for the stock and the market index.
    f. Compute and persist market-adjusted outcomes per horizon.
    g. Record a ModelRun for provenance.
    h. Commit and return the identifiers + outcomes.
    """
    now = datetime.now(UTC)

    # --- a. fetch + ingest disclosure ---
    raw = disclosure_provider.fetch_raw(ref)
    document = ingest_document(session, store, raw)

    # --- b. resolve instrument + link entities ---
    instrument = resolve_instrument(session, ticker, market=ref.market)
    if instrument is None:
        raise ValueError(
            f"Could not resolve an Instrument for ticker {ticker!r} "
            f"in market {ref.market!r}."
        )
    link_entities(session, document, [ticker])

    # --- c. extract structured event ---
    source_reliability = getattr(ref, "source_reliability", None)
    event_extraction, model_version = extractor.extract(
        raw.content, source_reliability=source_reliability
    )

    # --- d. persist event (impact hypothesis) ---
    # Fall back to a computed novelty score when the extractor leaves it null:
    # compare this disclosure against prior events' evidence for the same
    # instrument so a rehash of an already-recorded story scores low.
    resolved_novelty = event_extraction.novelty_score
    if resolved_novelty is None:
        resolved_novelty = _compute_prior_novelty(session, instrument.id, raw.content)

    model_id = getattr(extractor, "model", None) or _DEFAULT_MODEL
    event = Event(
        document_id=document.id,
        primary_instrument_id=instrument.id,
        event_type=event_extraction.event_type,
        entities=event_extraction.entities,
        industries=event_extraction.industries,
        channels=event_extraction.channels,
        direction=event_extraction.direction,
        horizon_days=event_extraction.horizon_days,
        surprise_score=event_extraction.surprise_score,
        novelty_score=resolved_novelty,
        source_reliability=event_extraction.source_reliability,
        confidence=event_extraction.confidence,
        evidence=event_extraction.evidence,
        model=model_id,
        model_version=model_version,
        analyzed_at=now,
    )
    session.add(event)
    session.flush()

    # --- e/f/f2. fetch prices, compute + persist outcomes and impacts ---
    event_date = document.published_at.date()
    outcomes, sector_index_ticker = _compute_and_persist_outcomes(
        session,
        event=event,
        instrument=instrument,
        ticker=ticker,
        market=ref.market,
        price_provider=price_provider,
        event_date=event_date,
        market_index_ticker=market_index_ticker,
        sector_index_ticker=sector_index_ticker,
        horizons=horizons,
        now=now,
    )

    # --- g. record provenance ---
    session.add(
        ModelRun(
            kind="vertical_slice",
            params={
                "ticker": ticker,
                "horizons": list(horizons),
                "sector_index_ticker": sector_index_ticker,
            },
            data_version=None,
            created_at=now,
        )
    )

    # --- h. commit + return ---
    session.commit()

    return SliceResult(
        document_id=document.id,
        event_id=event.id,
        instrument_id=instrument.id,
        outcomes=outcomes,
    )


def _compute_and_persist_outcomes(
    session,
    *,
    event,
    instrument,
    ticker: str,
    market: str,
    price_provider,
    event_date,
    market_index_ticker: str,
    sector_index_ticker: str | None,
    horizons: tuple[int, ...],
    now: datetime,
) -> tuple[list[OutcomeResult], str | None]:
    """Fetch prices and (re)persist outcomes + event_impacts for one event.

    Shared by :func:`run_slice` and :func:`recompute_document_outcomes`. Returns
    the computed outcomes and the sector index ticker actually used (resolved
    from the instrument's industry when not supplied), so the caller can record
    provenance. The sector-adjusted figure is supplementary: a missing mapping
    or a failed fetch degrades to market-adjusted only and never aborts.
    """
    window_start = event_date - timedelta(days=5)
    # Cover the longest horizon with slack for weekends/holidays: a 60 trading-day
    # horizon spans ~84 calendar days, so reserve well beyond that.
    max_horizon = max(horizons)
    window_end = event_date + timedelta(days=max_horizon * 2 + 15)

    stock_df = price_provider.get_ohlcv(ticker, window_start, window_end)
    market_df = price_provider.get_ohlcv(market_index_ticker, window_start, window_end)

    # Auto-resolve a sector benchmark from the instrument's industry unless the
    # caller passed one explicitly.
    if sector_index_ticker is None:
        sector_index_ticker = resolve_sector_index(market, instrument.industry)

    sector_df = None
    if sector_index_ticker is not None:
        try:
            sector_df = price_provider.get_ohlcv(
                sector_index_ticker, window_start, window_end
            )
        except Exception:  # noqa: BLE001 - sector data is optional; keep the core result
            logger.warning(
                "sector benchmark %s fetch failed; falling back to market-adjusted only",
                sector_index_ticker,
                exc_info=True,
            )
            sector_df = None

    ingest_prices(session, instrument.id, stock_df)

    outcomes = compute_event_outcomes(
        stock_df, market_df, event_date, horizons, sector_prices=sector_df
    )
    for result in outcomes:
        session.add(
            Outcome(
                event_id=event.id,
                instrument_id=instrument.id,
                horizon_days=result.horizon_days,
                raw_return=result.raw_return,
                market_return=result.market_return,
                abnormal_return=result.abnormal_return,
                sector_return=result.sector_return,
                sector_abnormal_return=result.sector_abnormal_return,
                computed_at=now,
            )
        )

    for impact in build_event_impacts(
        event, outcomes, industry=instrument.industry, computed_at=now
    ):
        session.add(impact)

    return outcomes, sector_index_ticker


def _needs_recompute(session, event, horizons: tuple[int, ...]) -> bool:
    """True when *event* is missing outcomes for the longest horizon or any impact row.

    Detects rows produced by an older engine (e.g. only the 1/5/20-day horizons,
    or outcomes without the paired ``event_impacts`` that ``/stats`` reads).
    """
    existing_horizons = set(
        session.scalars(
            select(Outcome.horizon_days).where(Outcome.event_id == event.id)
        ).all()
    )
    if not existing_horizons:
        return True
    if max(horizons) not in existing_horizons:
        return True
    impact_count = session.scalar(
        select(func.count())
        .select_from(EventImpact)
        .where(EventImpact.event_id == event.id)
    )
    return not impact_count


def recompute_document_outcomes(
    session,
    *,
    document,
    price_provider,
    ticker: str,
    market: str,
    market_index_ticker: str = "spy",
    sector_index_ticker: str | None = None,
    horizons: tuple[int, ...] = (1, 5, 20, 60),
    force: bool = False,
) -> int:
    """Recompute outcomes + event_impacts for events on an already-ingested document.

    Reuses each existing :class:`Event` (no LLM re-extraction, so no extraction
    cost and no duplicate events). For every event that ``_needs_recompute``
    flags — or all of them when *force* is set — the stale ``outcomes`` and
    ``event_impacts`` rows are deleted and recomputed with the current engine
    (full *horizons* incl. 60-day, sector-adjusted returns). Commits once and
    returns the number of events recomputed.

    Note: ``novelty_score`` is left as-is; backfilling it would require the raw
    disclosure text (re-extraction), which this fast path deliberately avoids.
    """
    now = datetime.now(UTC)
    events = list(
        session.scalars(select(Event).where(Event.document_id == document.id)).all()
    )
    event_date = document.published_at.date()
    recomputed = 0

    for event in events:
        if not force and not _needs_recompute(session, event, horizons):
            continue
        if event.primary_instrument_id is None:
            logger.warning(
                "recompute: event %s has no primary instrument; skipping", event.id
            )
            continue
        instrument = session.get(Instrument, event.primary_instrument_id)
        if instrument is None:
            logger.warning(
                "recompute: instrument %s for event %s missing; skipping",
                event.primary_instrument_id,
                event.id,
            )
            continue

        session.execute(delete(Outcome).where(Outcome.event_id == event.id))
        session.execute(delete(EventImpact).where(EventImpact.event_id == event.id))

        _compute_and_persist_outcomes(
            session,
            event=event,
            instrument=instrument,
            ticker=ticker,
            market=market,
            price_provider=price_provider,
            event_date=event_date,
            market_index_ticker=market_index_ticker,
            sector_index_ticker=sector_index_ticker,
            horizons=horizons,
            now=now,
        )
        recomputed += 1

    if recomputed:
        session.add(
            ModelRun(
                kind="recompute_outcomes",
                params={
                    "document_id": document.id,
                    "events": recomputed,
                    "horizons": list(horizons),
                },
                data_version=None,
                created_at=now,
            )
        )
    session.commit()
    return recomputed


def _compute_prior_novelty(session, instrument_id: int, candidate_text: str) -> float:
    """Novelty of *candidate_text* vs. prior events' evidence for an instrument.

    Returns ``1.0`` when there is no prior event on record for the instrument
    (fully novel), otherwise ``1.0 - max Jaccard similarity`` against the
    concatenated evidence sentences of each prior event.
    """
    rows = session.execute(
        select(Event.evidence).where(Event.primary_instrument_id == instrument_id)
    ).all()

    prior_texts: list[str] = []
    for (evidence,) in rows:
        if evidence:
            prior_texts.append(" ".join(str(s) for s in evidence))

    return novelty_score(candidate_text, prior_texts)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the ``markettrace-slice`` console script.

    Builds real providers, a real EventExtractor, and a real DB Session from
    settings, resolves the chosen DocumentRef, runs the slice, and prints the
    SliceResult as JSON. Intended for live use (requires network + API key);
    it does not run in CI.
    """
    parser = argparse.ArgumentParser(
        prog="markettrace-slice",
        description="Run the MarketTrace vertical-slice pipeline for one filing.",
    )
    parser.add_argument("--market", default="US", help="Market identifier (default: US).")
    parser.add_argument(
        "--issuer-id",
        default=None,
        help="Issuer id: CIK for US, corp_code for KR. Preferred over --cik.",
    )
    parser.add_argument(
        "--cik",
        default=None,
        help="Back-compat alias for --issuer-id (US CIK).",
    )
    parser.add_argument("--ticker", required=True, help="Primary ticker symbol.")
    parser.add_argument(
        "--accession",
        default=None,
        help=(
            "Specific filing id (US accession number / KR rcept_no); "
            "newest filing is used when omitted."
        ),
    )
    parser.add_argument(
        "--market-index",
        default=None,
        help="Benchmark index ticker (default: US 'spy', KR settings.kr_market_index_ticker).",
    )
    parser.add_argument(
        "--sector-index",
        default=None,
        help="Optional sector/industry benchmark ticker for sector-adjusted returns.",
    )
    args = parser.parse_args(argv)

    issuer_id = args.issuer_id if args.issuer_id is not None else args.cik
    if issuer_id is None:
        parser.error("one of --issuer-id or --cik is required")

    from markettrace.config import get_settings
    from markettrace.db.session import make_engine, make_session_factory
    from markettrace.nlp.event_extractor import EventExtractor
    from markettrace.providers.registry import (
        get_disclosure_provider,
        get_price_provider,
    )
    from markettrace.storage.object_store import ObjectStore

    settings = get_settings()

    if settings.active_api_key is None:
        key_env = "OPENAI_API_KEY" if settings.llm_provider == "openai" else "ANTHROPIC_API_KEY"
        print(
            f"error: {key_env} is not configured (LLM_PROVIDER={settings.llm_provider}); "
            "cannot run live extraction.",
            file=sys.stderr,
        )
        return 2

    if args.market == "US":
        disclosure_provider = get_disclosure_provider(
            args.market, user_agent=settings.sec_user_agent
        )
    else:
        disclosure_provider = get_disclosure_provider(args.market)
    price_provider = get_price_provider(args.market)
    extractor = EventExtractor()

    # Default benchmark index depends on the market unless overridden.
    if args.market_index is not None:
        market_index_ticker = args.market_index
    elif args.market == "KR":
        market_index_ticker = settings.kr_market_index_ticker
    else:
        market_index_ticker = "spy"

    # Resolve the chosen DocumentRef (newest filing, or a specific filing id).
    since = datetime(1970, 1, 1, tzinfo=UTC)
    refs = disclosure_provider.list_for_issuer(
        issuer_id, since, primary_ticker=args.ticker
    )
    if not refs:
        print(
            f"error: no filings found for issuer {issuer_id!r}.",
            file=sys.stderr,
        )
        return 1

    if args.accession is not None:
        ref = next((r for r in refs if r.external_id == args.accession), None)
        if ref is None:
            print(
                f"error: filing {args.accession!r} not found for issuer {issuer_id!r}.",
                file=sys.stderr,
            )
            return 1
    else:
        ref = max(refs, key=lambda r: r.published_at)

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    session = session_factory()
    store = ObjectStore(settings.object_store_dir)

    try:
        result = run_slice(
            session,
            store,
            ref=ref,
            disclosure_provider=disclosure_provider,
            price_provider=price_provider,
            extractor=extractor,
            ticker=args.ticker,
            market_index_ticker=market_index_ticker,
            sector_index_ticker=args.sector_index,
        )
    finally:
        session.close()

    payload = {
        "document_id": result.document_id,
        "event_id": result.event_id,
        "instrument_id": result.instrument_id,
        "outcomes": [
            {
                "horizon_days": o.horizon_days,
                "raw_return": o.raw_return,
                "market_return": o.market_return,
                "abnormal_return": o.abnormal_return,
                "sector_return": o.sector_return,
                "sector_abnormal_return": o.sector_abnormal_return,
            }
            for o in result.outcomes
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
