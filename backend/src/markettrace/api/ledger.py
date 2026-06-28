"""Login-gated API routes for turning card-statement PDFs into a ledger."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from markettrace.api.auth import require_auth
from markettrace.api.deps import get_db
from markettrace.api.schemas import (
    LedgerCategoryOut,
    LedgerEntryOut,
    LedgerRequest,
    LedgerStatementOut,
    LedgerStatementSummaryOut,
)
from markettrace.config import get_settings
from markettrace.ledger.statements import (
    StatementDependencyError,
    StatementError,
    StatementNotFoundError,
    StatementPasswordError,
    StatementPasswordRequiredError,
    parse_latest_statement,
    parse_statement_bytes,
    resolve_statement_dir,
)
from markettrace.ledger.storage import (
    aggregate_ledger_categories,
    build_ledger_statement_from_record,
    list_ledger_statements,
    save_ledger_statement,
    top_ledger_entries,
)
from markettrace.ledger.storage import (
    get_ledger_statement as get_saved_ledger_statement,
)

router = APIRouter()
_MAX_LEDGER_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/ledger/statement", response_model=LedgerStatementOut)
def get_ledger_statement(
    payload: LedgerRequest,
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> LedgerStatementOut:
    """Parse, save, and return the newest local card-statement PDF."""
    settings = get_settings()
    password = _resolve_statement_password(payload.password, settings.card_statement_password)
    statement_dir = resolve_statement_dir(settings.card_statement_dir)

    try:
        statement = parse_latest_statement(statement_dir, password)
    except StatementError as exc:
        raise _statement_http_exception(exc) from exc

    saved = save_ledger_statement(db, statement)
    return LedgerStatementOut.model_validate(build_ledger_statement_from_record(saved))


@router.post("/ledger/statement/upload", response_model=LedgerStatementOut)
async def upload_ledger_statement(
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> LedgerStatementOut:
    """Parse, save, and return an uploaded card-statement PDF."""
    file_name = file.filename or ""
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF file required")

    settings = get_settings()
    statement_password = _resolve_statement_password(password, settings.card_statement_password)

    data = await file.read(_MAX_LEDGER_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="empty statement file")
    if len(data) > _MAX_LEDGER_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="statement PDF is too large")

    try:
        statement = await run_in_threadpool(
            parse_statement_bytes,
            data=data,
            file_name=file_name,
            password=statement_password,
        )
    except StatementError as exc:
        raise _statement_http_exception(exc) from exc

    saved = save_ledger_statement(db, statement)
    return LedgerStatementOut.model_validate(build_ledger_statement_from_record(saved))


@router.get("/ledger/statements", response_model=list[LedgerStatementSummaryOut])
def list_saved_statements(
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[LedgerStatementSummaryOut]:
    """Return saved statements by month, newest first."""
    return [
        LedgerStatementSummaryOut.model_validate(row)
        for row in list_ledger_statements(db)
    ]


@router.get("/ledger/categories", response_model=list[LedgerCategoryOut])
def get_category_breakdown(
    month: str = Query(..., description="anchor month as YYYY-MM"),
    window: Literal["month", "year"] = Query("month"),
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[LedgerCategoryOut]:
    """Aggregate category totals for one month or the trailing 12 months."""
    bucket = _parse_statement_month(month)
    return [
        LedgerCategoryOut.model_validate(category)
        for category in aggregate_ledger_categories(db, month=bucket, window=window)
    ]


@router.get("/ledger/entries/top", response_model=list[LedgerEntryOut])
def get_top_entries(
    month: str = Query(..., description="anchor month as YYYY-MM"),
    window: Literal["month", "year"] = Query("month"),
    limit: int = Query(10, ge=1, le=50),
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[LedgerEntryOut]:
    """Return the highest-amount entries for one month or the trailing year."""
    bucket = _parse_statement_month(month)
    return [
        LedgerEntryOut.model_validate(entry)
        for entry in top_ledger_entries(db, month=bucket, window=window, limit=limit)
    ]


@router.get("/ledger/statements/{statement_month}", response_model=LedgerStatementOut)
def get_saved_statement(
    statement_month: str,
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> LedgerStatementOut:
    """Return a saved statement for ``YYYY-MM``."""
    row = get_saved_ledger_statement(db, _parse_statement_month(statement_month))
    if row is None:
        raise HTTPException(status_code=404, detail="statement not found")
    return LedgerStatementOut.model_validate(build_ledger_statement_from_record(row))


def _resolve_statement_password(
    supplied_password: str | None, configured_password: str | None
) -> str:
    password = (supplied_password or "").strip() or (configured_password or "").strip()
    if not password:
        raise _statement_http_exception(
            StatementPasswordRequiredError("statement password is required")
        )
    return password


def _parse_statement_month(value: str) -> date:
    parts = value.split("-")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="statement month must be YYYY-MM")
    try:
        year = int(parts[0])
        month = int(parts[1])
        return date(year, month, 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="statement month must be YYYY-MM"
        ) from exc


def _statement_http_exception(exc: StatementError) -> HTTPException:
    if isinstance(exc, StatementPasswordRequiredError):
        return HTTPException(status_code=400, detail="statement password required")
    if isinstance(exc, StatementPasswordError):
        return HTTPException(status_code=400, detail="invalid statement password")
    if isinstance(exc, StatementNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, StatementDependencyError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))
