"""Parse the latest local card-statement PDF into ledger entries."""

from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path

_DATE_LINE_RE = re.compile(r"^(?P<yy>\d{2})\.(?P<mm>\d{2})\.(?P<dd>\d{2})\s+(?P<rest>.+)$")
_MONEY_RE = re.compile(r"(?<![\d.])-?\d{1,3}(?:,\d{3})+(?![\d.])")
_FULL_DATE_RE = re.compile(r"20\d{2}\.\s*\d{2}\.\s*\d{2}")
_PERIOD_RE = re.compile(
    r"(20\d{2})\.\s*(\d{2})\.\s*(\d{2})\s*[^\d]{1,8}"
    r"(20\d{2})\.\s*(\d{2})\.\s*(\d{2})"
)
_OCR_DATE_RE = re.compile(r"^26[. ]*\d{2}[.: ]*\d{2}")
_LOGGER = logging.getLogger(__name__)


class StatementError(Exception):
    """Base class for statement parsing failures."""


class StatementNotFoundError(StatementError):
    """No statement PDF exists in the configured folder."""


class StatementPasswordRequiredError(StatementError):
    """The latest statement is encrypted and no password was supplied."""


class StatementPasswordError(StatementError):
    """The supplied statement password did not decrypt the PDF."""


class StatementDependencyError(StatementError):
    """A PDF parsing dependency is missing."""


@dataclass(frozen=True)
class LedgerEntry:
    date: date
    card_tail: str | None
    description: str
    amount: int
    category: str


@dataclass(frozen=True)
class LedgerCategory:
    category: str
    amount: int
    count: int


@dataclass(frozen=True)
class LedgerStatement:
    file_name: str
    file_modified_at: datetime
    encrypted: bool
    payment_due_date: date | None
    period_start: date | None
    period_end: date | None
    billed_total: int | None
    domestic_total: int | None
    foreign_total: int | None
    parsed_total: int
    entry_count: int
    entries: list[LedgerEntry]
    categories: list[LedgerCategory]
    warnings: list[str]


def resolve_statement_dir(configured_dir: str) -> Path:
    """Resolve a configured statement folder from common app working directories."""
    raw = Path(configured_dir).expanduser()
    candidates = [raw] if raw.is_absolute() else [Path.cwd() / raw, Path.cwd().parent / raw]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def parse_latest_statement(statement_dir: Path, password: str | None) -> LedgerStatement:
    """Read and parse the newest ``*.pdf`` in ``statement_dir``."""
    pdf_path = _find_latest_pdf(statement_dir)
    text, encrypted = _extract_pdf_text(pdf_path, password)
    merchant_overrides = _extract_ocr_merchants(pdf_path, password, text=text)
    modified_at = datetime.fromtimestamp(pdf_path.stat().st_mtime, tz=UTC)
    return parse_statement_text(
        text=text,
        file_name=pdf_path.name,
        file_modified_at=modified_at,
        encrypted=encrypted,
        merchant_overrides=merchant_overrides,
    )


def parse_statement_bytes(
    *, data: bytes, file_name: str, password: str | None
) -> LedgerStatement:
    """Parse an uploaded statement PDF without persisting the upload."""
    text, encrypted = _extract_pdf_text_from_bytes(data, password, file_name=file_name)
    merchant_overrides = _extract_ocr_merchants_from_bytes(
        data,
        password,
        text=text,
        file_name=file_name,
    )
    return parse_statement_text(
        text=text,
        file_name=file_name,
        file_modified_at=datetime.now(tz=UTC),
        encrypted=encrypted,
        merchant_overrides=merchant_overrides,
    )


def parse_statement_text(
    *,
    text: str,
    file_name: str,
    file_modified_at: datetime,
    encrypted: bool = False,
    merchant_overrides: list[str] | None = None,
) -> LedgerStatement:
    """Parse extracted card-statement text into a display-ready ledger."""
    payment_due_date = _parse_payment_due_date(text)
    period_start, period_end = _parse_period(text)
    billed_total, domestic_total, foreign_total = _parse_summary_totals(text)

    transaction_lines = _transaction_lines_from_text(text)
    entries = [
        entry
        for line in transaction_lines
        for entry in [_parse_entry(line)]
        if entry is not None
    ]
    if merchant_overrides:
        entries = [
            replace(entry, description=description, category=_categorize(description))
            for entry, description in zip(entries, merchant_overrides, strict=False)
        ] + entries[len(merchant_overrides) :]
    entries.sort(key=lambda e: (e.date, e.description, e.amount))

    parsed_total = sum(entry.amount for entry in entries)
    categories = _category_totals(entries)
    warnings = _build_warnings(
        text,
        entries,
        billed_total,
        parsed_total,
        has_ocr_merchants=bool(merchant_overrides),
    )

    return LedgerStatement(
        file_name=file_name,
        file_modified_at=file_modified_at,
        encrypted=encrypted,
        payment_due_date=payment_due_date,
        period_start=period_start,
        period_end=period_end,
        billed_total=billed_total,
        domestic_total=domestic_total,
        foreign_total=foreign_total,
        parsed_total=parsed_total,
        entry_count=len(entries),
        entries=entries,
        categories=categories,
        warnings=warnings,
    )


def _transaction_lines_from_text(text: str) -> list[str]:
    date_lines = [
        line.strip()
        for line in text.splitlines()
        if _DATE_LINE_RE.match(line.strip())
    ]
    has_foreign_detail = any(_is_foreign_detail_line(line) for line in date_lines)
    return [
        line
        for line in date_lines
        if not (has_foreign_detail and _is_foreign_summary_line(line))
    ]


def _find_latest_pdf(statement_dir: Path) -> Path:
    if not statement_dir.exists():
        raise StatementNotFoundError(f"statement folder not found: {statement_dir}")
    pdfs = [
        path
        for path in statement_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    ]
    if not pdfs:
        raise StatementNotFoundError(f"no PDF statements found in: {statement_dir}")
    return max(pdfs, key=lambda path: (path.stat().st_mtime, path.name))


def _extract_pdf_text(pdf_path: Path, password: str | None) -> tuple[str, bool]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    try:
        reader = PdfReader(str(pdf_path))
    except PdfReadError as exc:
        raise StatementError(f"could not read statement PDF: {pdf_path.name}") from exc
    return _extract_pdf_text_from_reader(reader, password)


def _extract_pdf_text_from_bytes(
    data: bytes, password: str | None, *, file_name: str
) -> tuple[str, bool]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise StatementError(f"could not read statement PDF: {file_name}") from exc
    return _extract_pdf_text_from_reader(reader, password)


def _extract_pdf_text_from_reader(reader, password: str | None) -> tuple[str, bool]:
    try:
        from pypdf.errors import FileNotDecryptedError
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    encrypted = bool(reader.is_encrypted)
    if encrypted:
        if not password:
            raise StatementPasswordRequiredError("statement password is required")
        if reader.decrypt(password) == 0:
            raise StatementPasswordError("statement password is invalid")

    try:
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except FileNotDecryptedError as exc:
        raise StatementPasswordError("statement password is invalid") from exc

    if not text.strip():
        raise StatementError("statement PDF did not contain extractable text")
    return text, encrypted


def _extract_ocr_merchants(pdf_path: Path, password: str | None, *, text: str) -> list[str]:
    """Best-effort OCR for merchant names.

    Card-statement text extraction preserves dates and amounts well, but this
    issuer's Korean merchant names are embedded with a custom font encoding.
    OCR replaces only that presentation field when a local macOS Vision path or
    the configured OpenAI fallback is available.
    """
    provider = _ledger_ocr_provider()
    if not _should_attempt_merchant_ocr(provider, text):
        return []

    if provider in ("auto", "swift"):
        merchants = _extract_swift_ocr_merchants(pdf_path, password)
        if merchants or provider == "swift":
            return merchants

    if provider in ("auto", "openai"):
        try:
            pdf_bytes = _read_decrypted_pdf_bytes(pdf_path, password)
        except StatementError:
            return []
        return _extract_openai_ocr_merchants_from_bytes(
            pdf_bytes,
            file_name=pdf_path.name,
            text=text,
        )

    return []


def _extract_ocr_merchants_from_bytes(
    data: bytes,
    password: str | None,
    *,
    text: str,
    file_name: str,
) -> list[str]:
    provider = _ledger_ocr_provider()
    if not _should_attempt_merchant_ocr(provider, text):
        return []

    if provider in ("auto", "swift"):
        merchants = _extract_swift_ocr_merchants_from_bytes(data, password)
        if merchants or provider == "swift":
            return merchants

    if provider in ("auto", "openai"):
        try:
            pdf_bytes = _read_decrypted_pdf_bytes_from_bytes(data, password)
        except StatementError:
            return []
        return _extract_openai_ocr_merchants_from_bytes(
            pdf_bytes,
            file_name=file_name,
            text=text,
        )

    return []


def _ledger_ocr_provider() -> str:
    try:
        from markettrace.config import get_settings
    except ImportError:
        return "none"

    return get_settings().ledger_ocr_provider


def _needs_merchant_ocr(text: str) -> bool:
    transaction_lines = _transaction_lines_from_text(text)
    if not transaction_lines:
        return False
    return "/Idiersis" in text or "»Î" in text


def _should_attempt_merchant_ocr(provider: str, text: str) -> bool:
    if provider == "none" or not _transaction_lines_from_text(text):
        return False
    if provider in ("swift", "openai"):
        return True
    if provider == "auto":
        return _needs_merchant_ocr(text) or _has_openai_ocr_config()
    return False


def _has_openai_ocr_config() -> bool:
    try:
        from markettrace.config import get_settings
    except ImportError:
        return False

    return bool(get_settings().openai_api_key)


def _extract_swift_ocr_merchants(pdf_path: Path, password: str | None) -> list[str]:
    swift = shutil.which("swift")
    script_path = Path(__file__).with_name("statement_ocr.swift")
    if not swift or not script_path.exists():
        return []

    temp_path: str | None = None
    try:
        temp_path = _write_decrypted_temp_pdf(pdf_path, password)
        proc = subprocess.run(
            [swift, str(script_path), temp_path],
            check=False,
            capture_output=True,
            text=True,
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError, StatementError):
        _LOGGER.debug("Swift merchant OCR failed", exc_info=True)
        return []
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        return []
    observations = _parse_ocr_observations(proc.stdout)
    return _merchant_names_from_ocr(observations)


def _extract_swift_ocr_merchants_from_bytes(data: bytes, password: str | None) -> list[str]:
    swift = shutil.which("swift")
    script_path = Path(__file__).with_name("statement_ocr.swift")
    if not swift or not script_path.exists():
        return []

    temp_path: str | None = None
    try:
        temp_path = _write_decrypted_temp_pdf_from_bytes(data, password)
        proc = subprocess.run(
            [swift, str(script_path), temp_path],
            check=False,
            capture_output=True,
            text=True,
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError, StatementError):
        _LOGGER.debug("Swift merchant OCR failed", exc_info=True)
        return []
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        return []
    observations = _parse_ocr_observations(proc.stdout)
    return _merchant_names_from_ocr(observations)


def _extract_openai_ocr_merchants_from_bytes(
    data: bytes,
    *,
    file_name: str,
    text: str,
) -> list[str]:
    try:
        from markettrace.config import get_settings
    except ImportError:
        return []

    settings = get_settings()
    if not settings.openai_api_key:
        return []

    transaction_lines = _transaction_lines_from_text(text)
    if not transaction_lines:
        return []

    try:
        import openai

        client = openai.OpenAI(api_key=settings.openai_api_key)
        content = _call_openai_merchant_ocr(
            client=client,
            model=settings.ledger_ocr_model,
            data=data,
            file_name=file_name,
            transaction_lines=transaction_lines,
        )
    except Exception:
        _LOGGER.warning("OpenAI merchant OCR failed", exc_info=True)
        return []

    merchants = _parse_openai_merchant_response(content)
    if not merchants:
        return []
    return merchants[: len(transaction_lines)]


def _call_openai_merchant_ocr(
    *,
    client,
    model: str,
    data: bytes,
    file_name: str,
    transaction_lines: list[str],
) -> str:
    encoded_pdf = base64.b64encode(data).decode("ascii")
    safe_file_name = Path(file_name).name or "statement.pdf"
    if not safe_file_name.lower().endswith(".pdf"):
        safe_file_name = f"{safe_file_name}.pdf"
    prompt = _openai_merchant_ocr_prompt(transaction_lines)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": safe_file_name,
                        "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                    },
                    {"type": "input_text", "text": prompt},
                ],
            }
        ],
        temperature=0,
    )
    return str(getattr(response, "output_text", "") or "")


def _openai_merchant_ocr_prompt(transaction_lines: list[str]) -> str:
    indexed_lines = "\n".join(
        f"{idx}. {line}" for idx, line in enumerate(transaction_lines, start=1)
    )
    return f"""\
Extract merchant names from this Korean card statement PDF.

Return strict JSON only in this shape:
{{"merchants":["merchant 1","merchant 2"]}}

Rules:
- Return exactly {len(transaction_lines)} merchant names.
- Preserve Korean merchant names exactly as shown in the PDF.
- Keep the order aligned with the parsed transaction lines below.
- Do not include dates, card numbers, amounts, approval numbers, installment
  labels, totals, or subtotals.
- Skip overseas summary rows that duplicate a detailed overseas transaction row.
- If a merchant cannot be read, use "가맹점명 인식 불가".

Parsed transaction lines:
{indexed_lines}
"""


def _parse_openai_merchant_response(content: str) -> list[str]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if isinstance(parsed, dict):
        values = parsed.get("merchants")
    else:
        values = parsed
    if not isinstance(values, list):
        return []

    merchants: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        merchant = _clean_ocr_merchant(value)
        if merchant:
            merchants.append(merchant)
    return merchants


def _read_decrypted_pdf_bytes(pdf_path: Path, password: str | None) -> bytes:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency already required upstream.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    reader = PdfReader(str(pdf_path))
    return _read_decrypted_pdf_bytes_from_reader(reader, password)


def _read_decrypted_pdf_bytes_from_bytes(data: bytes, password: str | None) -> bytes:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency already required upstream.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    reader = PdfReader(BytesIO(data))
    return _read_decrypted_pdf_bytes_from_reader(reader, password)


def _read_decrypted_pdf_bytes_from_reader(reader, password: str | None) -> bytes:
    try:
        from pypdf import PdfWriter
        from pypdf.errors import FileNotDecryptedError
    except ImportError as exc:  # pragma: no cover - dependency already required upstream.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    if reader.is_encrypted:
        if not password:
            raise StatementPasswordRequiredError("statement password is required")
        if reader.decrypt(password) == 0:
            raise StatementPasswordError("statement password is invalid")

    writer = PdfWriter()
    try:
        for page in reader.pages:
            writer.add_page(page)
    except FileNotDecryptedError as exc:
        raise StatementPasswordError("statement password is invalid") from exc

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _write_decrypted_temp_pdf(pdf_path: Path, password: str | None) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency already required upstream.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    reader = PdfReader(str(pdf_path))
    return _write_decrypted_temp_pdf_from_reader(reader, password)


def _write_decrypted_temp_pdf_from_bytes(data: bytes, password: str | None) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency already required upstream.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    reader = PdfReader(BytesIO(data))
    return _write_decrypted_temp_pdf_from_reader(reader, password)


def _write_decrypted_temp_pdf_from_reader(reader, password: str | None) -> str:
    try:
        from pypdf import PdfWriter
        from pypdf.errors import FileNotDecryptedError
    except ImportError as exc:  # pragma: no cover - dependency already required upstream.
        raise StatementDependencyError("pypdf is required to read card statement PDFs") from exc

    if reader.is_encrypted:
        if not password:
            raise StatementPasswordRequiredError("statement password is required")
        if reader.decrypt(password) == 0:
            raise StatementPasswordError("statement password is invalid")

    writer = PdfWriter()
    try:
        for page in reader.pages:
            writer.add_page(page)
    except FileNotDecryptedError as exc:
        raise StatementPasswordError("statement password is invalid") from exc

    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    with open(fd, "wb") as handle:
        writer.write(handle)
    return temp_path


def _parse_ocr_observations(output: str) -> list[dict]:
    rows: list[dict] = []
    for line in output.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("text"), str):
            rows.append(row)
    return rows


def _merchant_names_from_ocr(observations: list[dict]) -> list[str]:
    date_rows = [
        row
        for row in observations
        if row.get("page") in (2, 3)
        and float(row.get("x", 1)) < 0.09
        and _OCR_DATE_RE.search(str(row.get("text", "")).replace(" ", ""))
    ]
    merchants: list[tuple[int, float, str]] = []
    for date_row in date_rows:
        page = int(date_row["page"])
        y = float(date_row["y"])
        if page == 3 and 0.33 < y < 0.44:
            # Overseas summary rows duplicate the detailed overseas table below.
            continue
        segments = [
            row
            for row in observations
            if row.get("page") == page
            and 0.10 <= float(row.get("x", 1)) < 0.35
            and abs(float(row.get("y", 0)) - y) < 0.006
        ]
        raw = " ".join(str(row["text"]) for row in sorted(segments, key=lambda row: row["x"]))
        merchant = _clean_ocr_merchant(raw)
        if merchant:
            merchants.append((page, y, merchant))

    return [
        merchant
        for _, _, merchant in sorted(merchants, key=lambda row: (row[0], -row[1]))
    ]


def _clean_ocr_merchant(value: str) -> str:
    cleaned = re.sub(r"^[.•\s]+", "", value)
    cleaned = re.sub(r"본인\s*[0-9&]{2,3}\s*", "", cleaned)
    cleaned = re.sub(r"[.。·•]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-")
    if not cleaned:
        return ""
    if any(token in cleaned for token in ("일시불", "해외이용", "합계", "소계")):
        return ""
    return cleaned


def _parse_entry(line: str) -> LedgerEntry | None:
    match = _DATE_LINE_RE.match(line)
    if not match:
        return None

    rest = match.group("rest")
    amount_match = _last_money_match(rest)
    if amount_match is None:
        return None

    amount = int(amount_match.group(0).replace(",", ""))
    yy = int(match.group("yy"))
    year = 2000 + yy if yy < 70 else 1900 + yy
    used_on = date(year, int(match.group("mm")), int(match.group("dd")))

    card_match = re.search(r"»Î(?P<tail>\d{3})", rest)
    card_tail = card_match.group("tail") if card_match else None
    description_source = rest[: amount_match.start()]
    if card_match:
        description_source = description_source[card_match.end() :]
    description_source = re.split(r"\b(?:USD|KRW)\b", description_source, maxsplit=1)[0]
    description = _clean_description(description_source)

    return LedgerEntry(
        date=used_on,
        card_tail=card_tail,
        description=description,
        amount=amount,
        category=_categorize(description),
    )


def _last_money_match(value: str) -> re.Match[str] | None:
    matches = list(_MONEY_RE.finditer(value))
    if not matches:
        return None
    return matches[-1]


def _money_values(value: str) -> list[int]:
    return [int(match.group(0).replace(",", "")) for match in _MONEY_RE.finditer(value)]


def _clean_description(value: str) -> str:
    cleaned = value.replace("/Idiersis", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -−·")

    ascii_parts = re.findall(r"[A-Z][A-Z0-9&* .'/-]{1,}", cleaned)
    ascii_parts = [part.strip(" -") for part in ascii_parts if part.strip(" -")]
    if ascii_parts:
        return max(ascii_parts, key=len)
    return cleaned or "가맹점명 인식 불가"


def _categorize(description: str) -> str:
    upper = description.upper()
    if any(token in upper for token in ("GS THE FRESH", "KFC")):
        return "식비/마트"
    if any(token in upper for token in ("CU", "24")):
        return "편의점"
    if any(token in upper for token in ("KTX", "TAXI", "BUS", "TRAIN")):
        return "교통"
    if any(token in upper for token in ("KT", "SKT", "LG U", "0800")):
        return "통신"
    if any(
        token in upper
        for token in ("CLAUDE", "ANTHROPIC", "OPENAI", "RENDER", "GITHUB", "STEAM")
    ):
        return "구독/디지털"
    if any(token in upper for token in ("HAIR", "AORO")):
        return "미용"
    return "기타"


def _category_totals(entries: list[LedgerEntry]) -> list[LedgerCategory]:
    totals: dict[str, tuple[int, int]] = {}
    for entry in entries:
        amount, count = totals.get(entry.category, (0, 0))
        totals[entry.category] = (amount + entry.amount, count + 1)
    return [
        LedgerCategory(category=category, amount=amount, count=count)
        for category, (amount, count) in sorted(
            totals.items(), key=lambda item: item[1][0], reverse=True
        )
    ]


def _parse_payment_due_date(text: str) -> date | None:
    match = _FULL_DATE_RE.search(text)
    if not match:
        return None
    return _parse_full_date(match.group(0))


def _parse_period(text: str) -> tuple[date | None, date | None]:
    match = _PERIOD_RE.search(text)
    if not match:
        return None, None
    start = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    end = date(int(match.group(4)), int(match.group(5)), int(match.group(6)))
    return start, end


def _parse_full_date(value: str) -> date:
    y, m, d = [int(part) for part in re.findall(r"\d+", value)]
    return date(y, m, d)


def _parse_summary_totals(text: str) -> tuple[int | None, int | None, int | None]:
    due_match = _FULL_DATE_RE.search(text)
    if not due_match:
        return None, None, None
    values = _money_values(text[due_match.end() : due_match.end() + 500])
    if not values:
        return None, None, None
    billed = values[0]
    domestic = values[1] if len(values) > 1 else None
    foreign = values[2] if len(values) > 2 else None
    return billed, domestic, foreign


def _is_foreign_summary_line(line: str) -> bool:
    return " 2.00%" in line and not _is_foreign_detail_line(line)


def _is_foreign_detail_line(line: str) -> bool:
    return bool(re.search(r"\b(?:USD|KRW)\b", line))


def _build_warnings(
    text: str,
    entries: list[LedgerEntry],
    billed_total: int | None,
    parsed_total: int,
    *,
    has_ocr_merchants: bool,
) -> list[str]:
    warnings: list[str] = []
    if not entries:
        warnings.append("거래 라인을 찾지 못했습니다.")
    if ("/Idiersis" in text or "»Î" in text) and not has_ocr_merchants:
        warnings.append(
            "PDF 내장 글꼴 인코딩 때문에 일부 한글 가맹점명이 깨질 수 있습니다."
        )
    if billed_total is not None and parsed_total != billed_total:
        warnings.append(
            "청구금액과 파싱 거래 합계가 다릅니다. "
            "할부, 수수료, 할인, 중복 상세 내역을 확인하세요."
        )
    return warnings
