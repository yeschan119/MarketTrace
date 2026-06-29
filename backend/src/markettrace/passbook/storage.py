"""Persistence helpers for parsed passbook statements."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from markettrace.db.models import PassbookStatementRecord
from markettrace.passbook.statements import (
    PassbookCategory,
    PassbookEntry,
    PassbookStatement,
    categorize_summary,
    category_totals,
)


def resolve_statement_month(statement: PassbookStatement) -> date:
    """Return the month bucket used to store a parsed statement."""
    source_date = statement.period_end or statement.file_modified_at.date()
    return date(source_date.year, source_date.month, 1)


def save_passbook_statement(
    session: Session, statement: PassbookStatement, *, now: datetime | None = None
) -> PassbookStatementRecord:
    """Upsert one parsed statement per statement month."""
    statement_month = resolve_statement_month(statement)
    row = session.scalar(
        select(PassbookStatementRecord).where(
            PassbookStatementRecord.statement_month == statement_month
        )
    )
    if row is None:
        row = PassbookStatementRecord(statement_month=statement_month)
        session.add(row)

    row.file_name = statement.file_name
    row.file_modified_at = statement.file_modified_at
    row.uploaded_at = now or datetime.now(tz=UTC)
    row.encrypted = statement.encrypted
    row.account_no = statement.account_no
    row.account_holder = statement.account_holder
    row.period_start = statement.period_start
    row.period_end = statement.period_end
    row.closing_balance = statement.closing_balance
    row.withdrawal_total = statement.withdrawal_total
    row.deposit_total = statement.deposit_total
    row.entry_count = statement.entry_count
    row.entries = [_entry_payload(entry) for entry in statement.entries]
    row.categories = [_category_payload(category) for category in statement.categories]
    row.warnings = list(statement.warnings)

    session.commit()
    session.refresh(row)
    return row


def list_passbook_statements(session: Session) -> list[PassbookStatementRecord]:
    """Return saved statement summaries, newest month first."""
    return list(
        session.scalars(
            select(PassbookStatementRecord).order_by(
                PassbookStatementRecord.statement_month.desc()
            )
        )
    )


def _shift_months(value: date, months: int) -> date:
    """Return the first-of-month ``months`` before ``value``."""
    index = value.year * 12 + (value.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


def _entries_for_window(
    session: Session, *, month: date, window: str
) -> list[PassbookEntry]:
    """Return entries for a single month or a trailing 12 months."""
    start = _shift_months(month, 11) if window == "year" else month
    rows = session.scalars(
        select(PassbookStatementRecord)
        .where(
            PassbookStatementRecord.statement_month >= start,
            PassbookStatementRecord.statement_month <= month,
        )
        .order_by(PassbookStatementRecord.statement_month)
    )
    return [_entry_from_payload(entry) for row in rows for entry in row.entries]


def aggregate_passbook_categories(
    session: Session, *, month: date, window: str
) -> list[PassbookCategory]:
    """Aggregate category totals for a single month or a trailing 12 months."""
    return category_totals(_entries_for_window(session, month=month, window=window))


def top_passbook_entries(
    session: Session, *, month: date, window: str, direction: str, limit: int = 10
) -> list[PassbookEntry]:
    """Return the highest withdrawals or deposits for a month or trailing year."""
    entries = _entries_for_window(session, month=month, window=window)
    if direction == "in":
        entries = [entry for entry in entries if entry.deposit > 0]
        entries.sort(key=lambda entry: (-entry.deposit, entry.date, entry.description))
    else:
        entries = [entry for entry in entries if entry.withdrawal > 0]
        entries.sort(key=lambda entry: (-entry.withdrawal, entry.date, entry.description))
    return entries[:limit]


def get_passbook_statement(
    session: Session, statement_month: date
) -> PassbookStatementRecord | None:
    """Return one saved statement by month."""
    return session.scalar(
        select(PassbookStatementRecord).where(
            PassbookStatementRecord.statement_month == statement_month
        )
    )


def build_passbook_statement_from_record(
    row: PassbookStatementRecord,
) -> PassbookStatement:
    """Return a display statement from a saved row using current category rules."""
    entries = [_entry_from_payload(entry) for entry in row.entries]
    return PassbookStatement(
        statement_month=row.statement_month,
        uploaded_at=row.uploaded_at,
        file_name=row.file_name,
        file_modified_at=row.file_modified_at,
        encrypted=row.encrypted,
        account_no=row.account_no,
        account_holder=row.account_holder,
        period_start=row.period_start,
        period_end=row.period_end,
        closing_balance=row.closing_balance,
        withdrawal_total=row.withdrawal_total,
        deposit_total=row.deposit_total,
        entry_count=row.entry_count,
        entries=entries,
        categories=category_totals(entries),
        warnings=list(row.warnings),
    )


def _entry_payload(entry: PassbookEntry) -> dict:
    return {
        "date": entry.date.isoformat(),
        "time": entry.time,
        "summary": entry.summary,
        "direction": entry.direction,
        "amount": entry.amount,
        "withdrawal": entry.withdrawal,
        "deposit": entry.deposit,
        "description": entry.description,
        "balance": entry.balance,
        "branch": entry.branch,
        "category": entry.category,
    }


def _category_payload(category: PassbookCategory) -> dict:
    return {
        "category": category.category,
        "withdrawal": category.withdrawal,
        "deposit": category.deposit,
        "count": category.count,
    }


def _entry_from_payload(value: dict) -> PassbookEntry:
    summary = str(value.get("summary") or "")
    withdrawal = int(value.get("withdrawal") or 0)
    deposit = int(value.get("deposit") or 0)
    balance_raw = value.get("balance")
    return PassbookEntry(
        date=date.fromisoformat(str(value["date"])),
        time=str(value.get("time") or ""),
        summary=summary,
        direction=str(value.get("direction") or ("out" if withdrawal > 0 else "in")),
        amount=int(value.get("amount") or (withdrawal if withdrawal > 0 else deposit)),
        withdrawal=withdrawal,
        deposit=deposit,
        description=str(value.get("description") or ""),
        balance=int(balance_raw) if balance_raw is not None else None,
        branch=str(value.get("branch") or ""),
        category=categorize_summary(summary),
    )
