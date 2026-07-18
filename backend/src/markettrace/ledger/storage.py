"""Persistence helpers for parsed card statements."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import LedgerStatementRecord
from markettrace.ledger.customization import (
    CARD_DOMAIN,
    CategoryResolver,
    load_resolver,
)
from markettrace.ledger.statements import (
    LedgerCategory,
    LedgerEntry,
    LedgerStatement,
    categorize_description,
    category_totals,
)


def resolve_statement_month(statement: LedgerStatement) -> date:
    """Return the month bucket used to store a parsed statement."""
    source_date = (
        statement.period_end
        or statement.payment_due_date
        or statement.file_modified_at.date()
    )
    return date(source_date.year, source_date.month, 1)


def save_ledger_statement(
    session: Session, statement: LedgerStatement, *, now: datetime | None = None
) -> LedgerStatementRecord:
    """Upsert one parsed statement per statement month."""
    statement_month = resolve_statement_month(statement)
    row = session.scalar(
        select(LedgerStatementRecord).where(
            LedgerStatementRecord.statement_month == statement_month
        )
    )
    if row is None:
        row = LedgerStatementRecord(statement_month=statement_month)
        session.add(row)

    row.file_name = statement.file_name
    row.file_modified_at = statement.file_modified_at
    row.uploaded_at = now or datetime.now(tz=UTC)
    row.encrypted = statement.encrypted
    row.payment_due_date = statement.payment_due_date
    row.period_start = statement.period_start
    row.period_end = statement.period_end
    row.billed_total = statement.billed_total
    row.domestic_total = statement.domestic_total
    row.foreign_total = statement.foreign_total
    row.parsed_total = statement.parsed_total
    row.entry_count = statement.entry_count
    row.entries = [_entry_payload(entry) for entry in statement.entries]
    row.categories = [_category_payload(category) for category in statement.categories]
    row.warnings = list(statement.warnings)

    session.commit()
    session.refresh(row)
    return row


def list_ledger_statements(session: Session) -> list[LedgerStatementRecord]:
    """Return saved statement summaries, newest month first."""
    return list(
        session.scalars(
            select(LedgerStatementRecord).order_by(
                LedgerStatementRecord.statement_month.desc()
            )
        )
    )


def _shift_months(value: date, months: int) -> date:
    """Return the first-of-month ``months`` before ``value``."""
    index = value.year * 12 + (value.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


def _entries_for_window(
    session: Session, *, month: date, window: str
) -> list[LedgerEntry]:
    """Return ledger entries for a single month or a trailing 12 months."""
    start = _shift_months(month, 11) if window == "year" else month
    resolver = load_resolver(session, CARD_DOMAIN)
    rows = session.scalars(
        select(LedgerStatementRecord)
        .where(
            LedgerStatementRecord.statement_month >= start,
            LedgerStatementRecord.statement_month <= month,
        )
        .order_by(LedgerStatementRecord.statement_month)
    )
    return [
        _entry_from_payload(entry, resolver)
        for row in rows
        for entry in row.entries
    ]


def aggregate_ledger_categories(
    session: Session, *, month: date, window: str
) -> list[LedgerCategory]:
    """Aggregate category totals for a single month or a trailing 12 months."""
    return category_totals(_entries_for_window(session, month=month, window=window))


def top_ledger_entries(
    session: Session, *, month: date, window: str, limit: int = 10
) -> list[LedgerEntry]:
    """Return the highest-amount entries for a single month or a trailing year."""
    entries = _entries_for_window(session, month=month, window=window)
    entries.sort(key=lambda entry: (-entry.amount, entry.date, entry.description))
    return entries[:limit]


def get_ledger_statement(
    session: Session, statement_month: date
) -> LedgerStatementRecord | None:
    """Return one saved statement by month."""
    return session.scalar(
        select(LedgerStatementRecord).where(
            LedgerStatementRecord.statement_month == statement_month
        )
    )


def build_ledger_statement_from_record(
    row: LedgerStatementRecord, resolver: CategoryResolver | None = None
) -> LedgerStatement:
    """Return a display statement from a saved row using current category rules."""
    entries = [_entry_from_payload(entry, resolver) for entry in row.entries]
    return LedgerStatement(
        statement_month=row.statement_month,
        uploaded_at=row.uploaded_at,
        file_name=row.file_name,
        file_modified_at=row.file_modified_at,
        encrypted=row.encrypted,
        payment_due_date=row.payment_due_date,
        period_start=row.period_start,
        period_end=row.period_end,
        billed_total=row.billed_total,
        domestic_total=row.domestic_total,
        foreign_total=row.foreign_total,
        parsed_total=row.parsed_total,
        entry_count=row.entry_count,
        entries=entries,
        categories=category_totals(entries),
        warnings=list(row.warnings),
    )


def _entry_payload(entry: LedgerEntry) -> dict:
    return {
        "date": entry.date.isoformat(),
        "card_tail": entry.card_tail,
        "description": entry.description,
        "amount": entry.amount,
        "category": entry.category,
    }


def _category_payload(category: LedgerCategory) -> dict:
    return {
        "category": category.category,
        "amount": category.amount,
        "count": category.count,
    }


def _entry_from_payload(
    value: dict, resolver: CategoryResolver | None = None
) -> LedgerEntry:
    description = str(value.get("description") or "")
    entry = LedgerEntry(
        date=date.fromisoformat(str(value["date"])),
        card_tail=value.get("card_tail"),
        description=description,
        amount=int(value.get("amount") or 0),
        category=categorize_description(description),
    )
    if resolver is None:
        return entry
    resolved = resolver.category_for(
        entry_key=entry.entry_key,
        text=description,
        base_category=entry.category,
    )
    return entry if resolved == entry.category else replace(entry, category=resolved)
