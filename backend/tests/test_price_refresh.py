"""Tests for the recent-price refresh pipeline (drop screener prerequisite)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import polars as pl
from sqlalchemy import func
from sqlalchemy.orm import Session

from markettrace.db.models import Instrument, Price
from markettrace.pipeline.price_refresh import refresh_recent_prices

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


def _price_df(dates: list[str]) -> pl.DataFrame:
    n = len(dates)
    return pl.DataFrame(
        {
            "date": [
                pl.Series([d], dtype=pl.Utf8).str.to_date("%Y-%m-%d")[0] for d in dates
            ],
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.0 + i for i in range(n)],
            "adj_close": [100.0 + i for i in range(n)],
            "volume": [1_000_000.0 for _ in range(n)],
        }
    )


class _FakeProvider:
    """Records the (ticker, start, end) it was asked for and returns fixed bars."""

    def __init__(self, df: pl.DataFrame) -> None:
        self._df = df
        self.calls: list[tuple[str, date, date]] = []

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
        self.calls.append((ticker, start, end))
        return self._df


def _add_instrument(session: Session, market: str, ticker: str, **kw) -> Instrument:
    inst = Instrument(market=market, ticker=ticker, name=f"{ticker} Inc.", **kw)
    session.add(inst)
    session.flush()
    return inst


def test_refresh_inserts_recent_prices(db_session: Session) -> None:
    inst = _add_instrument(db_session, "US", "AAPL")
    provider = _FakeProvider(_price_df(["2026-02-25", "2026-02-26", "2026-02-27"]))

    inserted = refresh_recent_prices(
        db_session, [inst], lambda m: provider, now=_NOW, lookback_days=60
    )

    assert inserted == {inst.id: 3}
    count = (
        db_session.query(func.count(Price.id))
        .filter_by(instrument_id=inst.id)
        .scalar()
    )
    assert count == 3
    # Fetch window ends at now.date() and starts lookback_days earlier.
    ticker, start, end = provider.calls[0]
    assert ticker == "AAPL"
    assert end == date(2026, 3, 1)
    assert start == date(2026, 3, 1) - timedelta(days=60)


def test_refresh_is_idempotent(db_session: Session) -> None:
    inst = _add_instrument(db_session, "US", "AAPL")
    provider = _FakeProvider(_price_df(["2026-02-25", "2026-02-26"]))

    first = refresh_recent_prices(db_session, [inst], lambda m: provider, now=_NOW)
    second = refresh_recent_prices(db_session, [inst], lambda m: provider, now=_NOW)

    assert first == {inst.id: 2}
    assert second == {inst.id: 0}  # already present -> nothing new


def test_delisted_instruments_skipped(db_session: Session) -> None:
    live = _add_instrument(db_session, "US", "AAPL")
    dead = _add_instrument(
        db_session, "US", "OLD", delisted_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    provider = _FakeProvider(_price_df(["2026-02-26"]))

    inserted = refresh_recent_prices(
        db_session, [live, dead], lambda m: provider, now=_NOW
    )

    assert dead.id not in inserted
    assert inserted == {live.id: 1}


def test_provider_selected_per_market(db_session: Session) -> None:
    us = _add_instrument(db_session, "US", "AAPL")
    kr = _add_instrument(db_session, "KR", "005930")
    us_provider = _FakeProvider(_price_df(["2026-02-26"]))
    kr_provider = _FakeProvider(_price_df(["2026-02-26", "2026-02-27"]))
    providers = {"US": us_provider, "KR": kr_provider}

    inserted = refresh_recent_prices(
        db_session, [us, kr], lambda m: providers[m], now=_NOW
    )

    assert inserted == {us.id: 1, kr.id: 2}
    assert us_provider.calls[0][0] == "AAPL"
    assert kr_provider.calls[0][0] == "005930"


def test_failure_isolated_per_instrument(db_session: Session) -> None:
    good = _add_instrument(db_session, "US", "AAPL")
    bad = _add_instrument(db_session, "US", "BAD")

    class _Flaky:
        def get_ohlcv(self, ticker: str, start: date, end: date) -> pl.DataFrame:
            if ticker == "BAD":
                raise RuntimeError("provider blew up")
            return _price_df(["2026-02-26"])

    provider = _Flaky()
    inserted = refresh_recent_prices(
        db_session, [good, bad], lambda m: provider, now=_NOW
    )

    assert inserted == {good.id: 1, bad.id: 0}
    # The good instrument's row survived the bad one's rollback.
    assert (
        db_session.query(func.count(Price.id))
        .filter_by(instrument_id=good.id)
        .scalar()
    ) == 1
