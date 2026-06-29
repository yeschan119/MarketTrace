"""Login-gated API routes for turning bank-account PDFs into a passbook view."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from markettrace.api.auth import require_auth
from markettrace.api.deps import get_db
from markettrace.api.schemas import (
    PassbookCategoryOut,
    PassbookEntryOut,
    PassbookRequest,
    PassbookStatementOut,
    PassbookStatementSummaryOut,
)
from markettrace.config import get_settings
from markettrace.passbook.statements import (
    PassbookDependencyError,
    PassbookError,
    PassbookNotFoundError,
    PassbookPasswordError,
    PassbookPasswordRequiredError,
    parse_latest_passbook,
    parse_passbook_bytes,
    resolve_passbook_dir,
)
from markettrace.passbook.storage import (
    aggregate_passbook_categories,
    build_passbook_statement_from_record,
    list_passbook_statements,
    save_passbook_statement,
    top_passbook_entries,
)
from markettrace.passbook.storage import (
    get_passbook_statement as get_saved_passbook_statement,
)

router = APIRouter()
_MAX_PASSBOOK_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/passbook/statement", response_model=PassbookStatementOut)
def get_passbook_statement(
    payload: PassbookRequest,
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> PassbookStatementOut:
    """Parse, save, and return the newest local passbook PDF."""
    settings = get_settings()
    password = _resolve_passbook_password(payload.password, settings.passbook_password)
    passbook_dir = resolve_passbook_dir(settings.passbook_dir)

    try:
        statement = parse_latest_passbook(passbook_dir, password)
    except PassbookError as exc:
        raise _passbook_http_exception(exc) from exc

    saved = save_passbook_statement(db, statement)
    return PassbookStatementOut.model_validate(build_passbook_statement_from_record(saved))


@router.post("/passbook/statement/upload", response_model=PassbookStatementOut)
async def upload_passbook_statement(
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> PassbookStatementOut:
    """Parse, save, and return an uploaded passbook PDF."""
    file_name = file.filename or ""
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF file required")

    settings = get_settings()
    passbook_password = _resolve_passbook_password(password, settings.passbook_password)

    data = await file.read(_MAX_PASSBOOK_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="empty passbook file")
    if len(data) > _MAX_PASSBOOK_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="passbook PDF is too large")

    try:
        statement = await run_in_threadpool(
            parse_passbook_bytes,
            data=data,
            file_name=file_name,
            password=passbook_password,
        )
    except PassbookError as exc:
        raise _passbook_http_exception(exc) from exc

    saved = save_passbook_statement(db, statement)
    return PassbookStatementOut.model_validate(build_passbook_statement_from_record(saved))


@router.get("/passbook/statements", response_model=list[PassbookStatementSummaryOut])
def list_saved_statements(
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[PassbookStatementSummaryOut]:
    """Return saved statements by month, newest first."""
    return [
        PassbookStatementSummaryOut.model_validate(row)
        for row in list_passbook_statements(db)
    ]


@router.get("/passbook/categories", response_model=list[PassbookCategoryOut])
def get_category_breakdown(
    month: str = Query(..., description="anchor month as YYYY-MM"),
    window: Literal["month", "year"] = Query("month"),
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[PassbookCategoryOut]:
    """Aggregate category totals for one month or the trailing 12 months."""
    bucket = _parse_statement_month(month)
    return [
        PassbookCategoryOut.model_validate(category)
        for category in aggregate_passbook_categories(db, month=bucket, window=window)
    ]


@router.get("/passbook/entries/top", response_model=list[PassbookEntryOut])
def get_top_entries(
    month: str = Query(..., description="anchor month as YYYY-MM"),
    window: Literal["month", "year"] = Query("month"),
    direction: Literal["out", "in"] = Query("out"),
    limit: int = Query(10, ge=1, le=50),
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[PassbookEntryOut]:
    """Return the highest withdrawals or deposits for one month or the year."""
    bucket = _parse_statement_month(month)
    return [
        PassbookEntryOut.model_validate(entry)
        for entry in top_passbook_entries(
            db, month=bucket, window=window, direction=direction, limit=limit
        )
    ]


@router.get("/passbook/statements/{statement_month}", response_model=PassbookStatementOut)
def get_saved_statement(
    statement_month: str,
    _: None = Depends(require_auth),
    db: Session = Depends(get_db),
) -> PassbookStatementOut:
    """Return a saved statement for ``YYYY-MM``."""
    row = get_saved_passbook_statement(db, _parse_statement_month(statement_month))
    if row is None:
        raise HTTPException(status_code=404, detail="statement not found")
    return PassbookStatementOut.model_validate(build_passbook_statement_from_record(row))


def _resolve_passbook_password(
    supplied_password: str | None, configured_password: str | None
) -> str:
    password = (supplied_password or "").strip() or (configured_password or "").strip()
    if not password:
        raise _passbook_http_exception(
            PassbookPasswordRequiredError("passbook password is required")
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


def _passbook_http_exception(exc: PassbookError) -> HTTPException:
    if isinstance(exc, PassbookPasswordRequiredError):
        return HTTPException(status_code=400, detail="statement password required")
    if isinstance(exc, PassbookPasswordError):
        return HTTPException(status_code=400, detail="invalid statement password")
    if isinstance(exc, PassbookNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PassbookDependencyError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))
