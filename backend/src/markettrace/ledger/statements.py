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

from markettrace.ledger.fingerprint import make_entry_key

_DATE_LINE_RE = re.compile(r"^(?P<yy>\d{2})\.(?P<mm>\d{2})\.(?P<dd>\d{2})\s+(?P<rest>.+)$")
_MONEY_RE = re.compile(r"(?<![\d.])-?\d{1,3}(?:,\d{3})+(?![\d.])")
_FULL_DATE_RE = re.compile(r"20\d{2}\.\s*\d{2}\.\s*\d{2}")
_PERIOD_RE = re.compile(
    r"(20\d{2})\.\s*(\d{2})\.\s*(\d{2})\s*[^\d]{1,8}"
    r"(20\d{2})\.\s*(\d{2})\.\s*(\d{2})"
)
_OCR_DATE_RE = re.compile(r"^26[. ]*\d{2}[.: ]*\d{2}")
_OPENAI_OCR_RENDER_ZOOM = 3.0
_OPENAI_OCR_MAX_OUTPUT_TOKENS = 2000
_OPENAI_OCR_TIMEOUT_SECONDS = 45
_OPENAI_OCR_TABLE_CROP = (0.03, 0.08, 0.62, 0.97)
_OPENAI_OCR_TABLE_VERTICAL_SPLITS = 3
_OPENAI_OCR_TABLE_Y_OVERLAP = 0.015
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

    @property
    def entry_key(self) -> str:
        """Stable identity used to pin a manual category override to this row."""
        return make_entry_key(
            [self.date.isoformat(), self.card_tail or "", self.description, self.amount]
        )


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
    statement_month: date | None = None
    uploaded_at: datetime | None = None


@dataclass(frozen=True)
class _OcrMerchantRow:
    index: int | None
    used_on: date | None
    amount: int | None
    merchant: str


_UNREADABLE_MERCHANT = "가맹점명 인식 불가"
_OPENAI_MERCHANT_OCR_TEXT_FORMAT = {
    "type": "json_schema",
    "name": "card_statement_merchant_list",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "merchants": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "required": ["merchants"],
    },
}

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "구독/디지털",
        (
            "ADOBE",
            "ANTHROPIC",
            "APPLE.COM",
            "AWS",
            "CHATGPT",
            "CLAUDE",
            "CLOUDFLARE",
            "DISCORD",
            "DROPBOX",
            "FIGMA",
            "GITHUB",
            "GOOGLE",
            "MICROSOFT",
            "NETFLIX",
            "NOTION",
            "OPENAI",
            "RENDER",
            "SPOTIFY",
            "STEAM",
            "YOUTUBE",
            "구독",
            "멤버십",
            "애플코리아",
            "쿠팡와우",
        ),
    ),
    (
        "통신",
        (
            "0800",
            "KT",
            "LG U",
            "LGU",
            "SKT",
            "SK텔레콤",
            "U+",
            "인터넷",
            "케이티",
            "통신",
        ),
    ),
    (
        "교통",
        (
            "BUS",
            "KAKAO T",
            "KORAIL",
            "KTX",
            "SRT",
            "TAXI",
            "TMAP",
            "TRAIN",
            "공항철도",
            "버스",
            "지하철",
            "철도",
            "카카오T",
            "카카오택시",
            "코레일",
            "택시",
            "티머니",
        ),
    ),
    (
        "주유/차량",
        (
            "GS칼텍스",
            "PARKING",
            "S-OIL",
            "SK에너지",
            "고속도로",
            "세차",
            "주유",
            "주차",
            "충전소",
            "하이패스",
            "현대오일뱅크",
        ),
    ),
    (
        "마트/식료품",
        (
            "COSTCO",
            "EMART",
            "GS THE FRESH",
            "LOTTE MART",
            "SSG푸드마켓",
            "농협",
            "롯데마트",
            "마켓컬리",
            "마트",
            "슈퍼",
            "이마트",
            "지에스더프레시",
            "코스트코",
            "쿠팡프레시",
            "컬리",
            "트레이더스",
            "하나로마트",
            "홈플러스",
        ),
    ),
    (
        "편의점",
        (
            "CU",
            "EMART24",
            "GS25",
            "미니스톱",
            "세븐일레븐",
            "씨유",
            "이마트24",
            "편의점",
        ),
    ),
    (
        "카페/간식",
        (
            "BASKIN",
            "CAFE",
            "COFFEE",
            "STARBUCKS",
            "공차",
            "던킨",
            "디저트",
            "뚜레쥬르",
            "메가커피",
            "베스킨",
            "배스킨",
            "베이커리",
            "빽다방",
            "설빙",
            "스타벅스",
            "이디야",
            "카페",
            "커피",
            "컴포즈",
            "투썸",
            "파리바게뜨",
        ),
    ),
    (
        "배달",
        (
            "배달의민족",
            "배민",
            "요기요",
            "우아한형제들",
            "쿠팡이츠",
        ),
    ),
    (
        "외식",
        (
            "KFC",
            "MCDONALD",
            "갈비",
            "교촌",
            "국밥",
            "김밥",
            "김치",
            "달걀",
            "두부",
            "롯데리아",
            "맥도날드",
            "밥상",
            "버거",
            "버거킹",
            "보쌈",
            "분식",
            "서브웨이",
            "소바",
            "쌈밥",
            "식당",
            "음식점",
            "이자카야",
            "족발",
            "집밥",
            "치킨",
            "케이에프씨",
            "키친",
            "피자",
            "한식",
            "횟집",
        ),
    ),
    (
        "온라인쇼핑",
        (
            "11번가",
            "ALIEXPRESS",
            "AMAZON",
            "COUPANG",
            "G마켓",
            "NAVER PAY",
            "SSG.COM",
            "TEMU",
            "네이버페이",
            "옥션",
            "온라인",
            "카카오페이",
            "쿠팡",
            "테무",
        ),
    ),
    (
        "생활/쇼핑",
        (
            "ABC마트",
            "DAISO",
            "H&M",
            "OLIVE YOUNG",
            "ZARA",
            "다이소",
            "무신사",
            "생활용품",
            "쇼핑",
            "올리브영",
            "유니클로",
            "잡화",
        ),
    ),
    (
        "의료/약국",
        (
            "CLINIC",
            "MEDICAL",
            "PHARMACY",
            "내과",
            "병원",
            "약국",
            "안과",
            "의원",
            "이비인후과",
            "치과",
            "피부과",
            "한의원",
        ),
    ),
    (
        "자기계발",
        (
            "인프랩",
        ),
    ),
    (
        "교육/도서",
        (
            "ALADIN",
            "CLASS101",
            "INFLEARN",
            "UDEMY",
            "YES24",
            "강의",
            "교보문고",
            "도서",
            "서점",
            "알라딘",
            "예스24",
            "인프런",
            "클래스101",
            "학원",
        ),
    ),
    (
        "문화/여가",
        (
            "CGV",
            "PC방",
            "골프",
            "공연",
            "노래",
            "롯데시네마",
            "메가박스",
            "스포츠",
            "영화",
            "티켓",
            "필라테스",
            "헬스",
        ),
    ),
    (
        "여행/숙박",
        (
            "AGODA",
            "AIRBNB",
            "BOOKING",
            "HOTEL",
            "대한항공",
            "면세",
            "모텔",
            "숙박",
            "아고다",
            "아시아나",
            "여행",
            "제주항공",
            "진에어",
            "티웨이",
            "항공",
            "호텔",
        ),
    ),
    (
        "주거/공과금",
        (
            "관리비",
            "도시가스",
            "수도",
            "아파트",
            "월세",
            "전기",
            "한국전력",
        ),
    ),
    (
        "금융/보험/세금",
        (
            "국세",
            "보험",
            "세금",
            "수수료",
            "이자",
            "지방세",
        ),
    ),
    (
        "미용",
        (
            "AORO",
            "BARBER",
            "HAIR",
            "네일",
            "미용",
            "왁싱",
            "피부관리",
            "헤어",
        ),
    ),
    (
        "반려동물",
        (
            "PET",
            "동물병원",
            "반려",
            "애견",
            "펫",
        ),
    ),
)


@dataclass(frozen=True)
class _OcrImageChunk:
    transaction_lines: list[str]
    image_url: str


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


def _parseable_transaction_lines_from_text(text: str) -> list[str]:
    return [
        line for line in _transaction_lines_from_text(text) if _parse_entry(line) is not None
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
            text=text,
            required=provider == "openai",
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
            text=text,
            required=provider == "openai",
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
    text: str,
    required: bool = False,
) -> list[str]:
    try:
        from markettrace.config import get_settings
    except ImportError as exc:
        if required:
            raise StatementDependencyError("OpenAI OCR settings are unavailable") from exc
        return []

    settings = get_settings()
    if not settings.openai_api_key:
        if required:
            raise StatementDependencyError("OPENAI_API_KEY is required for card statement OCR")
        return []

    transaction_lines = _parseable_transaction_lines_from_text(text)
    if not transaction_lines:
        return []

    try:
        import openai

        chunks = _render_pdf_ocr_chunks(data, transaction_lines)
        client = openai.OpenAI(api_key=settings.openai_api_key, max_retries=0)
    except Exception:
        _LOGGER.warning("OpenAI merchant OCR setup failed", exc_info=True)
        if required:
            return [_UNREADABLE_MERCHANT for _ in transaction_lines]
        return []

    merchants: list[str] = []
    for chunk in chunks:
        try:
            content = _call_openai_merchant_ocr(
                client=client,
                model=settings.ledger_ocr_model,
                image_url=chunk.image_url,
                expected_count=len(chunk.transaction_lines),
            )
            chunk_merchants = _merchant_names_from_openai_response(content)
        except Exception:
            _LOGGER.warning("OpenAI merchant OCR failed", exc_info=True)
            chunk_merchants = []
        merchants.extend(_fit_merchant_count(chunk_merchants, len(chunk.transaction_lines)))

    if not merchants:
        return [_UNREADABLE_MERCHANT for _ in transaction_lines] if required else []
    return _fit_merchant_count(merchants, len(transaction_lines))


def _call_openai_merchant_ocr(
    *,
    client,
    model: str,
    image_url: str,
    expected_count: int,
) -> str:
    prompt = _openai_merchant_ocr_prompt(expected_count)
    response = client.responses.create(
        model=model,
        max_output_tokens=_OPENAI_OCR_MAX_OUTPUT_TOKENS,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_url, "detail": "high"},
                ],
            }
        ],
        temperature=0,
        text={"format": _OPENAI_MERCHANT_OCR_TEXT_FORMAT},
        timeout=_OPENAI_OCR_TIMEOUT_SECONDS,
    )
    return _response_output_text(response)


def _response_output_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    fragments: list[str] = []
    output = _object_value(response, "output")
    if isinstance(output, list):
        for item in output:
            content = _object_value(item, "content")
            if not isinstance(content, list):
                continue
            for part in content:
                text = _object_value(part, "text")
                if isinstance(text, str):
                    fragments.append(text)

    return "".join(fragments) or str(output_text or "")


def _object_value(value: object, key: str) -> object:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _render_pdf_ocr_chunks(
    data: bytes,
    transaction_lines: list[str],
) -> list[_OcrImageChunk]:
    try:
        import fitz
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - deployment dependency guard.
        raise StatementDependencyError("PyMuPDF and pypdf are required for card OCR") from exc

    chunks: list[_OcrImageChunk] = []
    reader = PdfReader(BytesIO(data))
    with fitz.open(stream=data, filetype="pdf") as document:
        matrix = fitz.Matrix(_OPENAI_OCR_RENDER_ZOOM, _OPENAI_OCR_RENDER_ZOOM)
        for page_index in _openai_ocr_page_indexes(document.page_count):
            if page_index >= len(reader.pages):
                continue
            page_lines = _parseable_transaction_lines_from_text(
                reader.pages[page_index].extract_text() or ""
            )
            if not page_lines:
                continue
            page = document.load_page(page_index)
            clips = _openai_ocr_table_clips(fitz, page.rect)
            for line_chunk, clip in zip(
                _split_sequence(page_lines, len(clips)),
                clips,
                strict=False,
            ):
                if not line_chunk:
                    continue
                pixmap = page.get_pixmap(matrix=matrix, alpha=False, clip=clip)
                encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
                chunks.append(
                    _OcrImageChunk(
                        transaction_lines=line_chunk,
                        image_url=f"data:image/png;base64,{encoded}",
                    )
                )

    chunk_line_count = sum(len(chunk.transaction_lines) for chunk in chunks)
    if chunk_line_count != len(transaction_lines):
        raise StatementError("card statement OCR row count did not match parsed entries")
    return chunks


def _split_sequence(values: list[str], count: int) -> list[list[str]]:
    if count <= 0:
        return [values]
    chunk_size = (len(values) + count - 1) // count
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


def _render_pdf_page_images(data: bytes) -> list[str]:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - deployment dependency guard.
        raise StatementDependencyError("PyMuPDF is required for card statement OCR") from exc

    images: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as document:
        matrix = fitz.Matrix(_OPENAI_OCR_RENDER_ZOOM, _OPENAI_OCR_RENDER_ZOOM)
        for page_index in _openai_ocr_page_indexes(document.page_count):
            page = document.load_page(page_index)
            for clip in _openai_ocr_table_clips(fitz, page.rect):
                pixmap = page.get_pixmap(matrix=matrix, alpha=False, clip=clip)
                encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
                images.append(f"data:image/png;base64,{encoded}")

    if not images:
        raise StatementError("statement PDF did not contain renderable pages")
    return images


def _openai_ocr_table_clips(fitz, page_rect) -> list:
    left, top, right, bottom = _OPENAI_OCR_TABLE_CROP
    table_height = bottom - top
    clips = []
    for split_index in range(_OPENAI_OCR_TABLE_VERTICAL_SPLITS):
        band_top = top + table_height * split_index / _OPENAI_OCR_TABLE_VERTICAL_SPLITS
        band_bottom = top + table_height * (split_index + 1) / _OPENAI_OCR_TABLE_VERTICAL_SPLITS
        if split_index > 0:
            band_top -= _OPENAI_OCR_TABLE_Y_OVERLAP
        if split_index < _OPENAI_OCR_TABLE_VERTICAL_SPLITS - 1:
            band_bottom += _OPENAI_OCR_TABLE_Y_OVERLAP
        clips.append(
            fitz.Rect(
                page_rect.x0 + page_rect.width * left,
                page_rect.y0 + page_rect.height * max(top, band_top),
                page_rect.x0 + page_rect.width * right,
                page_rect.y0 + page_rect.height * min(bottom, band_bottom),
            )
        )
    return clips


def _openai_ocr_page_indexes(page_count: int) -> list[int]:
    if page_count <= 0:
        return []
    if page_count >= 3:
        return [1, 2]
    return list(range(page_count))


def _openai_merchant_ocr_prompt(expected_count: int) -> str:
    return f"""\
Extract only merchant names from this cropped PNG section of a Korean card statement
transaction table.

Return JSON only in this shape:
{{"merchants":["merchant 1","merchant 2"]}}

Rules:
- This image section contains exactly {expected_count} transaction rows.
- Return exactly {expected_count} merchant strings in row order.
- Keep duplicate merchant rows. Keep rows with 0 amount or benefits.
- Preserve merchant names exactly as shown in the PDF.
- Prefer your best-effort Korean reading over "가맹점명 인식 불가" when text is visible.
- Do not include dates, card numbers, amounts, approval numbers, installment
  labels, benefits, point rates, totals, subtotals, or headers.
- If a merchant cannot be read, use "가맹점명 인식 불가".
"""


def _parse_openai_merchant_response(content: str) -> list[_OcrMerchantRow]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = _decode_embedded_json(raw)
        if parsed is None:
            return []

    if isinstance(parsed, dict):
        values = parsed.get("transactions") or parsed.get("rows") or parsed.get("merchants")
    else:
        values = parsed
    if not isinstance(values, list):
        return []

    rows: list[_OcrMerchantRow] = []
    for position, value in enumerate(values, start=1):
        if isinstance(value, str):
            merchant = _clean_ocr_merchant(value)
            if merchant:
                rows.append(
                    _OcrMerchantRow(
                        index=position,
                        used_on=None,
                        amount=None,
                        merchant=merchant,
                    )
                )
            continue
        if not isinstance(value, dict):
            continue
        merchant_value = value.get("merchant")
        merchant = _clean_ocr_merchant(str(merchant_value or ""))
        if merchant:
            rows.append(
                _OcrMerchantRow(
                    index=_parse_optional_int(value.get("index")),
                    used_on=_parse_ocr_row_date(value.get("date")),
                    amount=_parse_ocr_row_amount(value.get("amount")),
                    merchant=merchant,
                )
            )
    return rows


def _merchant_names_from_openai_response(content: str) -> list[str]:
    return [row.merchant for row in _parse_openai_merchant_response(content)]


def _fit_merchant_count(merchants: list[str], expected_count: int) -> list[str]:
    fitted = merchants[:expected_count]
    if len(fitted) < expected_count:
        fitted.extend([_UNREADABLE_MERCHANT] * (expected_count - len(fitted)))
    return fitted


def _decode_embedded_json(raw: str) -> object | None:
    decoder = json.JSONDecoder()
    for start, char in enumerate(raw):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue
        return parsed
    return None


def _match_ocr_rows_to_transaction_lines(
    transaction_lines: list[str],
    rows: list[_OcrMerchantRow],
) -> list[str]:
    entries = [_parse_entry(line) for line in transaction_lines]
    merchants = [_UNREADABLE_MERCHANT for _ in transaction_lines]
    used_row_indexes: set[int] = set()

    for row_index, row in enumerate(rows):
        target = row.index - 1 if row.index is not None else None
        if target is None or target < 0 or target >= len(entries):
            continue
        entry = entries[target]
        if entry is None:
            continue
        if _ocr_row_matches_entry(row, entry):
            merchants[target] = row.merchant
            used_row_indexes.add(row_index)

    for row_index, row in enumerate(rows):
        if row_index in used_row_indexes or row.used_on is None or row.amount is None:
            continue
        for entry_index, entry in enumerate(entries):
            if entry is None or merchants[entry_index] != _UNREADABLE_MERCHANT:
                continue
            if row.used_on == entry.date and row.amount == entry.amount:
                merchants[entry_index] = row.merchant
                used_row_indexes.add(row_index)
                break

    return merchants


def _ocr_row_matches_entry(row: _OcrMerchantRow, entry: LedgerEntry) -> bool:
    date_matches = row.used_on is None or row.used_on == entry.date
    amount_matches = row.amount is None or row.amount == entry.amount
    return date_matches and amount_matches


def _parse_optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = re.sub(r"[^\d-]", "", value)
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


def _parse_ocr_row_amount(value: object) -> int | None:
    return _parse_optional_int(value)


def _parse_ocr_row_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    numbers = [int(part) for part in re.findall(r"\d+", value)]
    if len(numbers) < 3:
        return None
    year, month, day = numbers[:3]
    if year < 100:
        year = 2000 + year if year < 70 else 1900 + year
    try:
        return date(year, month, day)
    except ValueError:
        return None


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
    return categorize_description(description)


def categorize_description(description: str) -> str:
    """Assign a display category from a merchant description."""
    if description == _UNREADABLE_MERCHANT:
        return "인식불가"
    normalized = _normalize_category_text(description)
    for category, tokens in _CATEGORY_RULES:
        if any(_normalize_category_text(token) in normalized for token in tokens):
            return category
    return "기타"


def _normalize_category_text(value: str) -> str:
    return re.sub(r"[\s._·•()/\\\\-]+", "", value.upper())


def _category_totals(entries: list[LedgerEntry]) -> list[LedgerCategory]:
    return category_totals(entries)


def category_totals(entries: list[LedgerEntry]) -> list[LedgerCategory]:
    """Aggregate ledger entries by category, largest amount first."""
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
    if any(entry.description == _UNREADABLE_MERCHANT for entry in entries):
        warnings.append("일부 가맹점명을 OCR로 읽지 못했습니다.")
    if billed_total is not None and parsed_total != billed_total:
        warnings.append(
            "청구금액과 파싱 거래 합계가 다릅니다. "
            "할부, 수수료, 할인, 중복 상세 내역을 확인하세요."
        )
    return warnings
