"""Idempotent instrument seeding.

The vertical-slice pipeline can only resolve an event to a company if the
corresponding :class:`Instrument` already exists in the database.  This module
seeds those rows -- either a single instrument from CLI flags or a small
built-in watchlist -- and is safe to run repeatedly (it never creates a
duplicate ``(market, ticker)``).
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from markettrace.db.models import Instrument

__all__ = ["DEFAULT_WATCHLIST", "seed_instrument", "seed_watchlist", "main"]

# Minimal starter universe: a couple of large caps plus the SPY benchmark used
# by the impact module as the market index.
DEFAULT_WATCHLIST: list[dict[str, str]] = [
    {"market": "US", "ticker": "AAPL", "name": "Apple Inc.", "industry": "Technology"},
    {"market": "US", "ticker": "MSFT", "name": "Microsoft Corporation", "industry": "Technology"},
    {"market": "US", "ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "industry": "Index"},
]


def seed_instrument(
    session: Session,
    *,
    market: str,
    ticker: str,
    name: str,
    industry: str | None = None,
) -> tuple[Instrument, bool]:
    """Insert an :class:`Instrument` if absent; return ``(instrument, created)``.

    Idempotent on ``(market, ticker)`` (case-insensitive ticker match).  When a
    matching row already exists it is returned unchanged with ``created=False``.
    """
    stmt = select(Instrument).where(
        func.lower(Instrument.market) == market.lower(),
        func.lower(Instrument.ticker) == ticker.lower(),
    )
    existing = session.scalars(stmt).first()
    if existing is not None:
        return existing, False

    instrument = Instrument(market=market, ticker=ticker, name=name, industry=industry)
    session.add(instrument)
    session.flush()
    return instrument, True


def seed_watchlist(
    session: Session,
    items: list[dict[str, str]],
) -> tuple[int, int]:
    """Seed every entry in *items*; return ``(created_count, skipped_count)``."""
    created = skipped = 0
    for item in items:
        _, was_created = seed_instrument(
            session,
            market=item["market"],
            ticker=item["ticker"],
            name=item["name"],
            industry=item.get("industry"),
        )
        if was_created:
            created += 1
        else:
            skipped += 1
    return created, skipped


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the ``markettrace-seed`` console script.

    With ``--ticker`` (and ``--name``) seeds a single instrument; otherwise
    seeds :data:`DEFAULT_WATCHLIST`.  Always idempotent.
    """
    parser = argparse.ArgumentParser(
        prog="markettrace-seed",
        description="Idempotently seed Instrument rows for the MarketTrace pipeline.",
    )
    parser.add_argument("--market", default="US", help="Market identifier (default: US).")
    parser.add_argument("--ticker", default=None, help="Ticker to seed; omit for watchlist.")
    parser.add_argument("--name", default=None, help="Instrument name (required with --ticker).")
    parser.add_argument("--industry", default=None, help="Optional industry/sector label.")
    args = parser.parse_args(argv)

    if args.ticker is not None and not args.name:
        print("error: --name is required when --ticker is given.", file=sys.stderr)
        return 2

    from markettrace.config import get_settings
    from markettrace.db.session import make_engine, make_session_factory

    settings = get_settings()
    engine = make_engine(settings.database_url)
    session = make_session_factory(engine)()

    try:
        if args.ticker is not None:
            items = [
                {
                    "market": args.market,
                    "ticker": args.ticker,
                    "name": args.name,
                    "industry": args.industry,
                }
            ]
        else:
            items = DEFAULT_WATCHLIST

        created, skipped = seed_watchlist(session, items)
        session.commit()
    finally:
        session.close()

    print(f"seeded: {created} created, {skipped} already present ({created + skipped} total)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
