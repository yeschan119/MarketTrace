"""Persistence helpers for parsed card statements."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import LedgerStatementRecord
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


def get_ledger_statement(
    session: Session, statement_month: date
) -> LedgerStatementRecord | None:
    """Return one saved statement by month."""
    return session.scalar(
        select(LedgerStatementRecord).where(
            LedgerStatementRecord.statement_month == statement_month
        )
    )


def build_ledger_statement_from_record(row: LedgerStatementRecord) -> LedgerStatement:
    """Return a display statement from a saved row using current category rules."""
    entries = [_entry_from_payload(entry) for entry in row.entries]
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


def _entry_from_payload(value: dict) -> LedgerEntry:
    description = str(value.get("description") or "")
    return LedgerEntry(
        date=date.fromisoformat(str(value["date"])),
        card_tail=value.get("card_tail"),
        description=description,
        amount=int(value.get("amount") or 0),
        category=categorize_description(description),
    )
