"""Entity linking: resolve tickers/names to Instrument rows and create DocumentEntity records."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from markettrace.db.models import DocumentEntity, EntityAlias, Instrument


def resolve_instrument(
    session: Session,
    ticker_or_name: str,
    market: str | None = None,
) -> Instrument | None:
    """Return the :class:`Instrument` matching *ticker_or_name*, or ``None``.

    Resolution order:
    1. Case-insensitive match on ``Instrument.ticker`` (optionally filtered by
       *market*).
    2. Case-insensitive match on ``EntityAlias.alias``.
    """
    # --- 1. Try ticker match ---
    stmt = select(Instrument).where(
        func.lower(Instrument.ticker) == ticker_or_name.lower()
    )
    if market is not None:
        stmt = stmt.where(func.lower(Instrument.market) == market.lower())
    instrument = session.scalars(stmt).first()
    if instrument is not None:
        return instrument

    # --- 2. Try alias match ---
    alias_stmt = (
        select(Instrument)
        .join(EntityAlias, EntityAlias.instrument_id == Instrument.id)
        .where(func.lower(EntityAlias.alias) == ticker_or_name.lower())
    )
    if market is not None:
        alias_stmt = alias_stmt.where(func.lower(Instrument.market) == market.lower())
    return session.scalars(alias_stmt).first()


def link_entities(
    session: Session,
    document,
    tickers: list[str],
) -> list[DocumentEntity]:
    """Create :class:`DocumentEntity` rows for every resolvable ticker in *tickers*.

    Confidence values:
    - ``1.0`` when the ticker matches ``Instrument.ticker`` exactly (case-insensitive).
    - ``0.7`` when the ticker matches via an ``EntityAlias``.

    Rows are added to the session and flushed (but not committed) before return.
    """
    created: list[DocumentEntity] = []

    for ticker in tickers:
        instrument = _resolve_with_confidence(session, ticker)
        if instrument is None:
            continue
        resolved_instrument, confidence = instrument

        entity = DocumentEntity(
            document_id=document.id,
            instrument_id=resolved_instrument.id,
            confidence=confidence,
        )
        session.add(entity)
        created.append(entity)

    if created:
        session.flush()

    return created


def _resolve_with_confidence(
    session: Session,
    ticker_or_name: str,
) -> tuple[Instrument, float] | None:
    """Return ``(Instrument, confidence)`` or ``None``.

    Confidence is 1.0 for a direct ticker match, 0.7 for an alias match.
    """
    # Direct ticker match → confidence 1.0
    stmt = select(Instrument).where(
        func.lower(Instrument.ticker) == ticker_or_name.lower()
    )
    instrument = session.scalars(stmt).first()
    if instrument is not None:
        return instrument, 1.0

    # Alias match → confidence 0.7
    alias_stmt = (
        select(Instrument)
        .join(EntityAlias, EntityAlias.instrument_id == Instrument.id)
        .where(func.lower(EntityAlias.alias) == ticker_or_name.lower())
    )
    instrument = session.scalars(alias_stmt).first()
    if instrument is not None:
        return instrument, 0.7

    return None
