"""Parse bank-account (passbook) transaction PDFs into a display-ready ledger.

The card-statement parser in :mod:`markettrace.ledger.statements` handles a
fixed-width issuer table that needs OCR for Korean merchant names. Bank
transaction PDFs are different: the text layer extracts cleanly, so this module
only has to reassemble visually-wrapped rows and split each row into columns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path

_RECORD_START_RE = re.compile(r"^(?P<date>\d{8})\s+(?P<time>\d{1,2}:\d{2}:\d{2})\s+(?P<body>.+)$")
_AMOUNT_TOKEN_RE = re.compile(r"^(?:0|\d{1,3}(?:,\d{3})*)$")
_COMMA_AMOUNT_RE = re.compile(r"^\d{1,3}(?:,\d{3})+$")
_PLAIN_INT_RE = re.compile(r"^\d+$")
_PERIOD_RE = re.compile(
    r"조회기간\s*(\d{4})\.(\d{2})\.(\d{2})\s*~\s*(\d{4})\.(\d{2})\.(\d{2})"
)
_ACCOUNT_NO_RE = re.compile(r"계좌번호\s*(?:\[[^\]]*\]\s*)?(?P<no>[\d*][\d*\-]+)")
_HOLDER_RE = re.compile(r"성명\s*(?P<name>\S+)")
_CLOSING_BALANCE_RE = re.compile(r"총잔액\s*(?P<amount>[\d,]+)")

_SKIP_LINE_MARKERS = (
    "SHINHAN BANK",
    "본 명세",
    "거래일자",
    "거래내역조회",
    "계좌번호",
    "조회기간",
    "출금가능금액",
    "총잔액",
)

_DIRECTION_OUT = "out"
_DIRECTION_IN = "in"


class PassbookError(Exception):
    """Base class for passbook parsing failures."""


class PassbookNotFoundError(PassbookError):
    """No passbook PDF exists in the configured folder."""


class PassbookPasswordRequiredError(PassbookError):
    """The passbook PDF is encrypted and no password was supplied."""


class PassbookPasswordError(PassbookError):
    """The supplied passbook password did not decrypt the PDF."""


class PassbookDependencyError(PassbookError):
    """A PDF parsing dependency is missing."""


@dataclass(frozen=True)
class PassbookEntry:
    date: date
    time: str
    summary: str
    direction: str
    amount: int
    withdrawal: int
    deposit: int
    description: str
    balance: int | None
    branch: str
    category: str


@dataclass(frozen=True)
class PassbookCategory:
    category: str
    withdrawal: int
    deposit: int
    count: int


@dataclass(frozen=True)
class PassbookStatement:
    file_name: str
    file_modified_at: datetime
    encrypted: bool
    account_no: str | None
    account_holder: str | None
    period_start: date | None
    period_end: date | None
    closing_balance: int | None
    withdrawal_total: int
    deposit_total: int
    entry_count: int
    entries: list[PassbookEntry]
    categories: list[PassbookCategory]
    warnings: list[str]
    statement_month: date | None = None
    uploaded_at: datetime | None = None


# Group raw 적요 (transaction-type) labels into friendly buckets. Order matters:
# more specific matches (타행/카드) are tested before broad ones. Anything that
# matches no rule keeps its cleaned 적요 text as the category.
_SUMMARY_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("카드결제", ("신한카드", "카드결제", "FB카드", "체크카드")),
    ("보험", ("FB보험", "보험")),
    ("이자", ("이자",)),
    ("공과금/세금", ("의보", "국세", "지방세", "세금", "건강보험", "공과금")),
    ("ATM/CD", ("효성CD", "CD공동망", "ATM", "현금")),
    ("자동이체(CMS)", ("CMS",)),
    ("펌뱅킹", ("펌뱅킹",)),
    ("타행이체", ("타행",)),
    ("인터넷뱅킹", ("인터넷뱅킹",)),
    ("모바일뱅킹", ("모바일",)),
    ("자동이체", ("자동이체",)),
)

# Known counterparties (내용) refine the 적요-based bucket — e.g. a deposit whose
# 적요 is merely "타행인터넷뱅킹" is really payroll when it comes from 코리안클로.
# These take priority over the 적요 rules above.
_DESCRIPTION_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("배달", ("우아한청년들",)),
    ("정부지원금", ("관악구",)),
    ("급여", ("코리안클로",)),
    ("월세", ("이건우",)),
    ("본인이체", ("강응찬",)),
    ("카드캐시백", ("마이신한포인트",)),
)


def resolve_passbook_dir(configured_dir: str) -> Path:
    """Resolve a configured passbook folder from common app working directories."""
    raw = Path(configured_dir).expanduser()
    candidates = [raw] if raw.is_absolute() else [Path.cwd() / raw, Path.cwd().parent / raw]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def parse_latest_passbook(passbook_dir: Path, password: str | None) -> PassbookStatement:
    """Read and parse the newest ``*.pdf`` in ``passbook_dir``."""
    pdf_path = _find_latest_pdf(passbook_dir)
    text, encrypted = _extract_pdf_text(pdf_path, password)
    modified_at = datetime.fromtimestamp(pdf_path.stat().st_mtime, tz=UTC)
    return parse_passbook_text(
        text=text,
        file_name=pdf_path.name,
        file_modified_at=modified_at,
        encrypted=encrypted,
    )


def parse_passbook_bytes(
    *, data: bytes, file_name: str, password: str | None
) -> PassbookStatement:
    """Parse an uploaded passbook PDF without persisting the upload."""
    text, encrypted = _extract_pdf_text_from_bytes(data, password, file_name=file_name)
    return parse_passbook_text(
        text=text,
        file_name=file_name,
        file_modified_at=datetime.now(tz=UTC),
        encrypted=encrypted,
    )


def parse_passbook_text(
    *,
    text: str,
    file_name: str,
    file_modified_at: datetime,
    encrypted: bool = False,
) -> PassbookStatement:
    """Parse extracted passbook text into a display-ready statement."""
    account_no = _parse_account_no(text)
    account_holder = _parse_holder(text)
    period_start, period_end = _parse_period(text)
    closing_balance = _parse_closing_balance(text)

    entries = [
        entry
        for record in _transaction_records_from_text(text)
        for entry in [_parse_record(record)]
        if entry is not None
    ]
    entries.sort(key=lambda e: (e.date, e.time, e.description))

    withdrawal_total = sum(entry.withdrawal for entry in entries)
    deposit_total = sum(entry.deposit for entry in entries)
    categories = category_totals(entries)
    warnings = _build_warnings(entries, closing_balance)

    return PassbookStatement(
        file_name=file_name,
        file_modified_at=file_modified_at,
        encrypted=encrypted,
        account_no=account_no,
        account_holder=account_holder,
        period_start=period_start,
        period_end=period_end,
        closing_balance=closing_balance,
        withdrawal_total=withdrawal_total,
        deposit_total=deposit_total,
        entry_count=len(entries),
        entries=entries,
        categories=categories,
        warnings=warnings,
    )


def _transaction_records_from_text(text: str) -> list[str]:
    """Reassemble transaction rows that the PDF wraps across several lines.

    A row always starts with ``YYYYMMDD HH:MM:SS``. Wrapped continuation lines
    split a token mid-word, so continuations are joined with no separator.
    """
    records: list[str] = []
    buffer: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _is_skip_line(line):
            if buffer is not None:
                records.append(buffer)
                buffer = None
            continue
        if _RECORD_START_RE.match(line):
            if buffer is not None:
                records.append(buffer)
            buffer = line
        elif buffer is not None:
            buffer += line
    if buffer is not None:
        records.append(buffer)
    return records


def _is_skip_line(line: str) -> bool:
    return any(marker in line for marker in _SKIP_LINE_MARKERS)


def _parse_record(record: str) -> PassbookEntry | None:
    match = _RECORD_START_RE.match(record)
    if not match:
        return None

    used_on = _parse_record_date(match.group("date"))
    if used_on is None:
        return None
    time_str = match.group("time")
    tokens = match.group("body").split()

    pair_index = _find_amount_pair(tokens)
    if pair_index is None:
        return None

    summary = " ".join(tokens[:pair_index]).strip()
    withdrawal = _to_int(tokens[pair_index])
    deposit = _to_int(tokens[pair_index + 1])
    tail = tokens[pair_index + 2 :]

    balance_index = _find_balance_index(tail)
    if balance_index is None:
        description = " ".join(tail).strip()
        balance: int | None = None
        branch = ""
    else:
        description = " ".join(tail[:balance_index]).strip()
        balance = _to_int(tail[balance_index])
        branch = " ".join(tail[balance_index + 1 :]).strip()

    direction = _DIRECTION_OUT if withdrawal > 0 else _DIRECTION_IN
    amount = withdrawal if withdrawal > 0 else deposit

    return PassbookEntry(
        date=used_on,
        time=time_str,
        summary=summary or "기타",
        direction=direction,
        amount=amount,
        withdrawal=withdrawal,
        deposit=deposit,
        description=description or "내용 없음",
        balance=balance,
        branch=branch,
        category=categorize(summary, description),
    )


def _find_amount_pair(tokens: list[str]) -> int | None:
    """Return the index of the first 출금/입금 amount-token pair."""
    for index in range(len(tokens) - 1):
        if _AMOUNT_TOKEN_RE.match(tokens[index]) and _AMOUNT_TOKEN_RE.match(tokens[index + 1]):
            return index
    return None


def _find_balance_index(tail: list[str]) -> int | None:
    """Return the index of the 잔액 token in the trailing 내용/잔액/거래점 region."""
    balance_index: int | None = None
    for index, token in enumerate(tail):
        if _COMMA_AMOUNT_RE.match(token):
            balance_index = index
    if balance_index is not None:
        return balance_index
    for index, token in enumerate(tail):
        if _PLAIN_INT_RE.match(token):
            balance_index = index
    return balance_index


def _to_int(token: str) -> int:
    return int(token.replace(",", ""))


def categorize(summary: str, description: str) -> str:
    """Pick a category, letting a known counterparty (내용) override the 적요."""
    normalized_desc = _normalize_category_text(description or "")
    if normalized_desc:
        for category, tokens in _DESCRIPTION_CATEGORY_RULES:
            if any(_normalize_category_text(token) in normalized_desc for token in tokens):
                return category
    return categorize_summary(summary)


def categorize_summary(summary: str) -> str:
    """Assign a display category from a 적요 (transaction-type) label."""
    cleaned = re.sub(r"\s+", " ", summary or "").strip()
    if not cleaned:
        return "기타"
    normalized = _normalize_category_text(cleaned)
    for category, tokens in _SUMMARY_CATEGORY_RULES:
        if any(_normalize_category_text(token) in normalized for token in tokens):
            return category
    return cleaned


def _normalize_category_text(value: str) -> str:
    return re.sub(r"[\s._·•()/\\-]+", "", value.upper())


def category_totals(entries: list[PassbookEntry]) -> list[PassbookCategory]:
    """Aggregate entries by category, tracking withdrawals and deposits apart."""
    totals: dict[str, tuple[int, int, int]] = {}
    for entry in entries:
        withdrawal, deposit, count = totals.get(entry.category, (0, 0, 0))
        totals[entry.category] = (
            withdrawal + entry.withdrawal,
            deposit + entry.deposit,
            count + 1,
        )
    return [
        PassbookCategory(category=category, withdrawal=withdrawal, deposit=deposit, count=count)
        for category, (withdrawal, deposit, count) in sorted(
            totals.items(),
            key=lambda item: (item[1][0] + item[1][1]),
            reverse=True,
        )
    ]


def _find_latest_pdf(passbook_dir: Path) -> Path:
    if not passbook_dir.exists():
        raise PassbookNotFoundError(f"passbook folder not found: {passbook_dir}")
    pdfs = [
        path
        for path in passbook_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    ]
    if not pdfs:
        raise PassbookNotFoundError(f"no PDF statements found in: {passbook_dir}")
    return max(pdfs, key=lambda path: (path.stat().st_mtime, path.name))


def _extract_pdf_text(pdf_path: Path, password: str | None) -> tuple[str, bool]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent.
        raise PassbookDependencyError("pypdf is required to read passbook PDFs") from exc

    try:
        reader = PdfReader(str(pdf_path))
    except PdfReadError as exc:
        raise PassbookError(f"could not read passbook PDF: {pdf_path.name}") from exc
    return _extract_pdf_text_from_reader(reader, password)


def _extract_pdf_text_from_bytes(
    data: bytes, password: str | None, *, file_name: str
) -> tuple[str, bool]:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent.
        raise PassbookDependencyError("pypdf is required to read passbook PDFs") from exc

    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise PassbookError(f"could not read passbook PDF: {file_name}") from exc
    return _extract_pdf_text_from_reader(reader, password)


def _extract_pdf_text_from_reader(reader, password: str | None) -> tuple[str, bool]:
    try:
        from pypdf.errors import FileNotDecryptedError
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent.
        raise PassbookDependencyError("pypdf is required to read passbook PDFs") from exc

    encrypted = bool(reader.is_encrypted)
    if encrypted:
        if not password:
            raise PassbookPasswordRequiredError("passbook password is required")
        if reader.decrypt(password) == 0:
            raise PassbookPasswordError("passbook password is invalid")

    try:
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except FileNotDecryptedError as exc:
        raise PassbookPasswordError("passbook password is invalid") from exc
    except Exception as exc:  # pragma: no cover - depends on optional crypto backend.
        raise PassbookDependencyError(
            "cryptography is required to decrypt this passbook PDF"
        ) from exc

    if not text.strip():
        raise PassbookError("passbook PDF did not contain extractable text")
    return text, encrypted


def _parse_record_date(value: str) -> date | None:
    if len(value) != 8:
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None


def _parse_account_no(text: str) -> str | None:
    match = _ACCOUNT_NO_RE.search(text)
    return match.group("no") if match else None


def _parse_holder(text: str) -> str | None:
    match = _HOLDER_RE.search(text)
    return match.group("name") if match else None


def _parse_period(text: str) -> tuple[date | None, date | None]:
    match = _PERIOD_RE.search(text)
    if not match:
        return None, None
    start = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    end = date(int(match.group(4)), int(match.group(5)), int(match.group(6)))
    return start, end


def _parse_closing_balance(text: str) -> int | None:
    match = _CLOSING_BALANCE_RE.search(text)
    if not match:
        return None
    return _to_int(match.group("amount"))


def _build_warnings(
    entries: list[PassbookEntry], closing_balance: int | None
) -> list[str]:
    warnings: list[str] = []
    if not entries:
        warnings.append("거래 라인을 찾지 못했습니다.")
        return warnings
    if closing_balance is not None and entries:
        latest = max(entries, key=lambda e: (e.date, e.time))
        if latest.balance is not None and latest.balance != closing_balance:
            warnings.append(
                "총잔액과 최근 거래의 잔액이 다릅니다. 누락된 거래가 있는지 확인하세요."
            )
    return warnings
