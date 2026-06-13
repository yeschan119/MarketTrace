"""Tests for idempotent instrument seeding (markettrace-seed)."""

from __future__ import annotations

from sqlalchemy import func, select

from markettrace.db.models import Instrument
from markettrace.pipeline.seed import (
    DEFAULT_WATCHLIST,
    seed_instrument,
    seed_watchlist,
)


def _count(session, market: str, ticker: str) -> int:
    stmt = select(func.count()).select_from(Instrument).where(
        func.lower(Instrument.market) == market.lower(),
        func.lower(Instrument.ticker) == ticker.lower(),
    )
    return session.scalar(stmt)


class TestSeedInstrument:
    def test_creates_new_instrument(self, db_session):
        inst, created = seed_instrument(
            db_session, market="US", ticker="AAPL", name="Apple Inc.", industry="Technology"
        )
        assert created is True
        assert inst.id is not None
        assert inst.ticker == "AAPL"
        assert _count(db_session, "US", "AAPL") == 1

    def test_second_run_is_idempotent(self, db_session):
        first, c1 = seed_instrument(db_session, market="US", ticker="AAPL", name="Apple Inc.")
        second, c2 = seed_instrument(db_session, market="US", ticker="AAPL", name="Apple Inc.")
        assert c1 is True
        assert c2 is False
        assert second.id == first.id
        assert _count(db_session, "US", "AAPL") == 1

    def test_match_is_case_insensitive_on_ticker(self, db_session):
        seed_instrument(db_session, market="US", ticker="AAPL", name="Apple Inc.")
        _, created = seed_instrument(db_session, market="US", ticker="aapl", name="Apple Inc.")
        assert created is False
        assert _count(db_session, "US", "AAPL") == 1


class TestSeedWatchlist:
    def test_seeds_default_watchlist(self, db_session):
        created, skipped = seed_watchlist(db_session, DEFAULT_WATCHLIST)
        assert created == len(DEFAULT_WATCHLIST)
        assert skipped == 0
        total = db_session.scalar(select(func.count()).select_from(Instrument))
        assert total == len(DEFAULT_WATCHLIST)

    def test_rerun_skips_all(self, db_session):
        seed_watchlist(db_session, DEFAULT_WATCHLIST)
        created, skipped = seed_watchlist(db_session, DEFAULT_WATCHLIST)
        assert created == 0
        assert skipped == len(DEFAULT_WATCHLIST)
        total = db_session.scalar(select(func.count()).select_from(Instrument))
        assert total == len(DEFAULT_WATCHLIST)

    def test_default_watchlist_includes_spy_benchmark(self):
        tickers = {item["ticker"] for item in DEFAULT_WATCHLIST}
        assert "SPY" in tickers
