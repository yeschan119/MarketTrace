"""Login-gated API routes for turning card-statement PDFs into a ledger."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from markettrace.api.auth import require_auth
from markettrace.api.schemas import LedgerRequest, LedgerStatementOut
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

router = APIRouter()
_MAX_LEDGER_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/ledger/statement", response_model=LedgerStatementOut)
def get_ledger_statement(
    payload: LedgerRequest, _: None = Depends(require_auth)
) -> LedgerStatementOut:
    """Return a parsed ledger from the newest local card-statement PDF."""
    settings = get_settings()
    password = _resolve_statement_password(payload.password, settings.card_statement_password)
    statement_dir = resolve_statement_dir(settings.card_statement_dir)

    try:
        statement = parse_latest_statement(statement_dir, password)
    except StatementError as exc:
        raise _statement_http_exception(exc) from exc

    return LedgerStatementOut.model_validate(statement)


@router.post("/ledger/statement/upload", response_model=LedgerStatementOut)
async def upload_ledger_statement(
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    _: None = Depends(require_auth),
) -> LedgerStatementOut:
    """Return a parsed ledger from an uploaded card-statement PDF."""
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

    return LedgerStatementOut.model_validate(statement)


def _resolve_statement_password(
    supplied_password: str | None, configured_password: str | None
) -> str:
    password = (supplied_password or "").strip() or (configured_password or "").strip()
    if not password:
        raise _statement_http_exception(
            StatementPasswordRequiredError("statement password is required")
        )
    return password


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
