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
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from markettrace.db.models import Event, ModelRun, Outcome
from markettrace.impact.returns import OutcomeResult, compute_event_outcomes
from markettrace.ingest.disclosures import ingest_document
from markettrace.ingest.prices import ingest_prices
from markettrace.nlp.entity_linker import link_entities, resolve_instrument
from markettrace.providers.base import DocumentRef

__all__ = ["SliceResult", "run_slice", "main"]

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
    horizons: tuple[int, ...] = (1, 5, 20),
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
        novelty_score=event_extraction.novelty_score,
        source_reliability=event_extraction.source_reliability,
        confidence=event_extraction.confidence,
        evidence=event_extraction.evidence,
        model=model_id,
        model_version=model_version,
        analyzed_at=now,
    )
    session.add(event)
    session.flush()

    # --- e. fetch price window for stock + market index ---
    event_date = document.published_at.date()
    window_start = event_date - timedelta(days=5)
    window_end = event_date + timedelta(days=40)

    stock_df = price_provider.get_ohlcv(ticker, window_start, window_end)
    market_df = price_provider.get_ohlcv(market_index_ticker, window_start, window_end)

    ingest_prices(session, instrument.id, stock_df)

    # --- f. compute + persist outcomes ---
    outcomes = compute_event_outcomes(stock_df, market_df, event_date, horizons)
    for result in outcomes:
        session.add(
            Outcome(
                event_id=event.id,
                instrument_id=instrument.id,
                horizon_days=result.horizon_days,
                raw_return=result.raw_return,
                market_return=result.market_return,
                abnormal_return=result.abnormal_return,
                computed_at=now,
            )
        )

    # --- g. record provenance ---
    session.add(
        ModelRun(
            kind="vertical_slice",
            params={"ticker": ticker, "horizons": list(horizons)},
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
            }
            for o in result.outcomes
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
