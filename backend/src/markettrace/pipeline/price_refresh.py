"""Recent-price refresh — the data prerequisite for the drop screener (Feature 1).

Prices in this system are ingested only in windows *around events*
(:func:`markettrace.pipeline.vertical_slice`), so the DB has no continuous,
up-to-date daily series for the universe. The drop screener needs a trailing
20-trading-day window ending near today for every tracked name; computing a
drawdown off stale event-window bars would be a silent freshness bug
(blueprint §9).

This pipeline closes that gap: for each (non-delisted) instrument it fetches the
last ``lookback_days`` of OHLCV from the market's configured price provider and
upserts it. It reuses :func:`markettrace.ingest.prices.ingest_prices`, which
skips ``(instrument_id, date)`` pairs already present, so re-running only fills
in newly-closed bars — idempotent and cheap to repeat (free-tier friendly).

Like the other ingest CLIs it commits per instrument, so a mid-run timeout
leaves earlier instruments persisted and a re-run resumes.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from markettrace.db.models import Instrument
from markettrace.ingest.prices import ingest_prices
from markettrace.providers.base import PriceProvider

__all__ = ["DEFAULT_LOOKBACK_DAYS", "refresh_recent_prices", "main"]

logger = logging.getLogger(__name__)

# Calendar-day lookback. ~60 days comfortably covers the 20 *trading* days the
# screener's high needs, with slack for weekends/holidays.
DEFAULT_LOOKBACK_DAYS = 60


def refresh_recent_prices(
    session,
    instruments: Iterable[Instrument],
    provider_for: Callable[[str], PriceProvider],
    *,
    now: datetime,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[int, int]:
    """Fetch + upsert the last ``lookback_days`` of prices for each instrument.

    ``provider_for`` maps a market string to a :class:`PriceProvider` (injected
    so tests use fakes and the CLI reuses one rate-limited client per market).
    Delisted instruments are skipped. Each instrument is isolated: a failed
    fetch is logged, rolled back, and recorded as 0 so the rest still persist.
    Commits after each instrument. Returns inserted-row counts keyed by
    instrument id.
    """
    end = now.date()
    start = end - timedelta(days=lookback_days)

    inserted: dict[int, int] = {}
    for inst in instruments:
        if inst.delisted_at is not None:
            continue
        try:
            provider = provider_for(inst.market)
            price_df = provider.get_ohlcv(inst.ticker, start, end)
            count = ingest_prices(session, inst.id, price_df)
            session.commit()
            inserted[inst.id] = count
        except Exception:  # noqa: BLE001 - one instrument must not abort the rest
            session.rollback()
            logger.exception(
                "price refresh: instrument %s (%s/%s) failed; skipping",
                inst.id,
                inst.market,
                inst.ticker,
            )
            inserted[inst.id] = 0

    return inserted


def _load_instruments(session, markets: Sequence[str] | None) -> list[Instrument]:
    stmt = select(Instrument).where(Instrument.delisted_at.is_(None))
    if markets:
        stmt = stmt.where(Instrument.market.in_(markets))
    return list(session.scalars(stmt.order_by(Instrument.market, Instrument.ticker)))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``markettrace-refresh-prices`` (live; needs price keys).

    Builds real price providers (one per market, cached) and a DB session from
    settings, refreshes the last ``--lookback-days`` of prices for the tracked
    universe, and prints a summary as JSON. Not run in CI.
    """
    parser = argparse.ArgumentParser(
        prog="markettrace-refresh-prices",
        description="Refresh recent daily prices for the tracked universe.",
    )
    parser.add_argument(
        "--market",
        default=None,
        help="Comma-separated markets to limit to (e.g. 'US,KR'); default all.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Calendar-day lookback window (default {DEFAULT_LOOKBACK_DAYS}).",
    )
    args = parser.parse_args(argv)

    from markettrace.config import get_settings
    from markettrace.db.session import make_engine, make_session_factory
    from markettrace.providers.registry import get_price_provider

    settings = get_settings()
    markets = (
        [m.strip().upper() for m in args.market.split(",") if m.strip()]
        if args.market
        else None
    )

    # One provider per market, built lazily and reused (rate-limited clients).
    provider_cache: dict[str, PriceProvider] = {}

    def provider_for(market: str) -> PriceProvider:
        if market not in provider_cache:
            provider_cache[market] = get_price_provider(market)
        return provider_cache[market]

    engine = make_engine(settings.database_url)
    session = make_session_factory(engine)()
    try:
        instruments = _load_instruments(session, markets)
        if not instruments:
            print("error: no matching instruments to refresh.", file=sys.stderr)
            return 2
        inserted = refresh_recent_prices(
            session, instruments, provider_for, now=datetime.now(UTC),
            lookback_days=args.lookback_days,
        )
    finally:
        session.close()

    total = sum(inserted.values())
    print(
        json.dumps(
            {
                "instruments": len(inserted),
                "rows_inserted": total,
                "by_instrument": inserted,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
