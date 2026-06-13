"""Price ingest — upsert OHLCV rows from a polars DataFrame.

Skips rows where an (instrument_id, date) pair already exists so the
operation is safe to run repeatedly with overlapping date ranges.
"""

from __future__ import annotations

from datetime import date

import polars as pl
from sqlalchemy.orm import Session

from markettrace.db.models import Price

__all__ = ["ingest_prices"]


def ingest_prices(
    session: Session,
    instrument_id: int,
    price_df: pl.DataFrame,
) -> int:
    """Upsert price rows for ``instrument_id`` from ``price_df``.

    Existing ``(instrument_id, date)`` pairs are silently skipped.

    Parameters
    ----------
    session:
        An open SQLAlchemy ``Session``; the caller is responsible for committing.
    instrument_id:
        FK referencing ``instruments.id``.
    price_df:
        Polars DataFrame with columns: date (pl.Date), open, high, low,
        close, adj_close, volume.

    Returns
    -------
    int
        Number of rows actually inserted.
    """
    # Collect existing dates for this instrument to skip duplicates.
    existing_dates: set[date] = {
        row[0]
        for row in session.query(Price.date).filter_by(instrument_id=instrument_id).all()
    }

    inserted = 0
    for row in price_df.iter_rows(named=True):
        row_date: date = row["date"]
        if row_date in existing_dates:
            continue

        session.add(
            Price(
                instrument_id=instrument_id,
                date=row_date,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                adj_close=row["adj_close"],
                volume=row["volume"],
            )
        )
        existing_dates.add(row_date)
        inserted += 1

    if inserted:
        session.flush()

    return inserted
