"""Tests for card-statement ledger parsing and API auth gating."""

from __future__ import annotations

import base64
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import markettrace.api.ledger as ledger_api
import markettrace.ledger.statements as statement_mod
from markettrace.api.auth import create_token
from markettrace.api.deps import get_db
from markettrace.api.main import create_app
from markettrace.db.models import Base, LedgerStatementRecord
from markettrace.ledger.statements import (
    LedgerCategory,
    LedgerEntry,
    LedgerStatement,
    parse_statement_text,
)


def _sample_statement_text() -> str:
    return """
    2026.07.01 account
    1,716,664
    1,634,970
    81,694
    text period 2026. 05. 18 - 2026. 06. 17
    26.05.26 »Î069 GS THE FRESH sample 17,580
    26.06.09 »Î881 KFC sample 11,500 0.70%
    26.06.07 »Î881 OPENAI *CHATGPT SUBSCR 29,000 29,769 52 2.00%
    26.06.07 »Î881 test OPENAI.COM OPENAI *CHATGPT SUBSCR KRW 29,000 19.11 1,557.80 52 29,821
    """


def test_parse_statement_text_extracts_summary_entries_and_categories() -> None:
    statement = parse_statement_text(
        text=_sample_statement_text(),
        file_name="statement.pdf",
        file_modified_at=datetime(2026, 6, 26, tzinfo=UTC),
        encrypted=True,
    )

    assert statement.encrypted is True
    assert statement.payment_due_date.isoformat() == "2026-07-01"
    assert statement.period_start.isoformat() == "2026-05-18"
    assert statement.period_end.isoformat() == "2026-06-17"
    assert statement.billed_total == 1_716_664
    assert statement.domestic_total == 1_634_970
    assert statement.foreign_total == 81_694
    # The foreign summary line is dropped when a detailed foreign line exists.
    assert statement.entry_count == 3
    assert statement.parsed_total == 17_580 + 11_500 + 29_821
    assert [entry.description for entry in statement.entries] == [
        "GS THE FRESH",
        "OPENAI.COM OPENAI *CHATGPT SUBSCR",
        "KFC",
    ]
    assert {category.category for category in statement.categories} >= {
        "마트/식료품",
        "외식",
        "구독/디지털",
    }


def test_parse_statement_text_applies_merchant_overrides() -> None:
    statement = parse_statement_text(
        text=_sample_statement_text(),
        file_name="statement.pdf",
        file_modified_at=datetime(2026, 6, 26, tzinfo=UTC),
        merchant_overrides=["지에스더프레시", "오픈AI 구독", "케이에프씨"],
    )

    assert [entry.description for entry in statement.entries] == [
        "지에스더프레시",
        "케이에프씨",
        "오픈AI 구독",
    ]
    assert [entry.category for entry in statement.entries] == [
        "마트/식료품",
        "외식",
        "구독/디지털",
    ]
    assert statement.warnings == [
        "청구금액과 파싱 거래 합계가 다릅니다. 할부, 수수료, 할인, 중복 상세 내역을 확인하세요."
    ]


def test_parse_statement_text_uses_granular_korean_categories() -> None:
    statement = parse_statement_text(
        text="""
        2026.07.01 account
        100,000
        100,000
        0
        text period 2026. 05. 01 - 2026. 05. 31
        26.05.01 »Î001 unreadable one 1,000
        26.05.02 »Î001 unreadable two 2,000
        26.05.03 »Î001 unreadable three 3,000
        26.05.04 »Î001 unreadable four 4,000
        26.05.05 »Î001 unreadable five 5,000
        26.05.06 »Î001 unreadable six 6,000
        26.05.07 »Î001 unreadable seven 7,000
        26.05.08 »Î001 unreadable eight 8,000
        26.05.09 »Î001 unreadable nine 9,000
        26.05.10 »Î001 unreadable ten 10,000
        """,
        file_name="statement.pdf",
        file_modified_at=datetime(2026, 6, 26, tzinfo=UTC),
        merchant_overrides=[
            "스타벅스",
            "쿠팡",
            "올리브영",
            "서울치과",
            "한국전력",
            "GS칼텍스",
            "CGV",
            "교보문고",
            "아고다",
            statement_mod._UNREADABLE_MERCHANT,
        ],
    )

    assert [entry.category for entry in statement.entries] == [
        "카페/간식",
        "온라인쇼핑",
        "생활/쇼핑",
        "의료/약국",
        "주거/공과금",
        "주유/차량",
        "문화/여가",
        "교육/도서",
        "여행/숙박",
        "인식불가",
    ]


def test_openai_ocr_fallback_extracts_merchant_names(monkeypatch) -> None:
    settings = SimpleNamespace(
        openai_api_key="test-key",
        ledger_ocr_model="gpt-4o-mini",
    )
    seen: dict[str, object] = {}

    class _FakeResponses:
        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                output_text=(
                    '{"merchants":["지에스더프레시","케이에프씨"]}'
                )
            )

    class _FakeOpenAI:
        def __init__(self, *, api_key: str, max_retries: int) -> None:
            seen["api_key"] = api_key
            seen["max_retries"] = max_retries
            self.responses = _FakeResponses()

    fake_openai = SimpleNamespace(OpenAI=_FakeOpenAI)
    monkeypatch.setattr("markettrace.config.get_settings", lambda: settings)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    def fake_render_chunks(data, transaction_lines):
        seen["transaction_lines"] = transaction_lines
        return [
            statement_mod._OcrImageChunk(
                transaction_lines=transaction_lines,
                image_url="data:image/png;base64,test-image",
            )
        ]

    monkeypatch.setattr(statement_mod, "_render_pdf_ocr_chunks", fake_render_chunks)

    merchants = statement_mod._extract_openai_ocr_merchants_from_bytes(
        b"%PDF-1.7",
        text="\n".join(
            [
                "26.05.26 »Î069 broken text 17,580",
                "26.05.26 »Î069 broken text 800",
                "26.06.09 »Î881 broken text 11,500",
            ]
        ),
    )

    assert merchants == ["지에스더프레시", "케이에프씨"]
    assert seen["api_key"] == "test-key"
    assert seen["max_retries"] == 0
    assert seen["transaction_lines"] == [
        "26.05.26 »Î069 broken text 17,580",
        "26.06.09 »Î881 broken text 11,500",
    ]
    assert seen["model"] == "gpt-4o-mini"
    assert seen["max_output_tokens"] == statement_mod._OPENAI_OCR_MAX_OUTPUT_TOKENS
    assert seen["text"] == {"format": statement_mod._OPENAI_MERCHANT_OCR_TEXT_FORMAT}
    assert seen["timeout"] == statement_mod._OPENAI_OCR_TIMEOUT_SECONDS
    request = seen["input"][0]["content"]
    assert request[0]["type"] == "input_text"
    assert "exactly 2 transaction rows" in request[0]["text"]
    assert request[1] == {
        "type": "input_image",
        "image_url": "data:image/png;base64,test-image",
        "detail": "high",
    }


def test_ocr_rows_match_by_date_amount_and_mark_unmatched() -> None:
    rows = statement_mod._parse_openai_merchant_response(
        '{"transactions":[{"date":"2026-06-09","amount":"11,500","merchant":"케이에프씨"}]}'
    )

    merchants = statement_mod._match_ocr_rows_to_transaction_lines(
        [
            "26.05.26 »Î069 broken text 17,580",
            "26.06.09 »Î881 broken text 11,500",
        ],
        rows,
    )

    assert merchants == [statement_mod._UNREADABLE_MERCHANT, "케이에프씨"]


def test_openai_response_text_reads_output_content_without_helper_property() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="output_text",
                        text='{"transactions":[{"index":1,"date":"2026-06-09",',
                    ),
                    {
                        "type": "output_text",
                        "text": '"amount":11500,"merchant":"케이에프씨"}]}',
                    },
                ]
            )
        ]
    )

    assert statement_mod._response_output_text(response) == (
        '{"transactions":[{"index":1,"date":"2026-06-09",'
        '"amount":11500,"merchant":"케이에프씨"}]}'
    )


def test_parse_openai_merchant_response_extracts_embedded_json() -> None:
    rows = statement_mod._parse_openai_merchant_response(
        'Result: {"transactions":[{"index":1,"date":"2026-06-09",'
        '"amount":11500,"merchant":"케이에프씨"}]}'
    )

    assert rows == [
        statement_mod._OcrMerchantRow(
            index=1,
            used_on=datetime(2026, 6, 9, tzinfo=UTC).date(),
            amount=11_500,
            merchant="케이에프씨",
        )
    ]


def test_openai_provider_runs_even_without_known_garbled_markers(monkeypatch) -> None:
    settings = SimpleNamespace(
        ledger_ocr_provider="openai",
        openai_api_key="test-key",
        ledger_ocr_model="gpt-4o-mini",
    )

    monkeypatch.setattr("markettrace.config.get_settings", lambda: settings)
    monkeypatch.setattr(
        statement_mod,
        "_read_decrypted_pdf_bytes_from_bytes",
        lambda *_: b"%PDF-1.7",
    )
    monkeypatch.setattr(
        statement_mod,
        "_extract_openai_ocr_merchants_from_bytes",
        lambda *_, **__: ["스타벅스"],
    )

    merchants = statement_mod._extract_ocr_merchants_from_bytes(
        b"raw-pdf",
        None,
        text="26.05.26 garbled merchant text 5,000",
        file_name="statement.pdf",
    )

    assert merchants == ["스타벅스"]


def test_required_openai_ocr_returns_unreadable_placeholder_without_rows(monkeypatch) -> None:
    settings = SimpleNamespace(
        ledger_ocr_provider="openai",
        openai_api_key="test-key",
        ledger_ocr_model="gpt-4o-mini",
    )

    monkeypatch.setattr("markettrace.config.get_settings", lambda: settings)
    monkeypatch.setattr(
        statement_mod,
        "_read_decrypted_pdf_bytes_from_bytes",
        lambda *_: b"%PDF-1.7",
    )
    monkeypatch.setattr(
        statement_mod,
        "_render_pdf_ocr_chunks",
        lambda _, lines: [
            statement_mod._OcrImageChunk(
                transaction_lines=lines,
                image_url="data:image/png;base64,test-image",
            )
        ],
    )
    monkeypatch.setattr(
        statement_mod,
        "_call_openai_merchant_ocr",
        lambda *_, **__: '{"merchants":[]}',
    )

    merchants = statement_mod._extract_ocr_merchants_from_bytes(
        b"raw-pdf",
        None,
        text="26.05.26 garbled merchant text 5,000",
        file_name="statement.pdf",
    )

    assert merchants == [statement_mod._UNREADABLE_MERCHANT]


def test_required_openai_ocr_returns_unreadable_placeholder_on_failure(monkeypatch) -> None:
    settings = SimpleNamespace(
        openai_api_key="test-key",
        ledger_ocr_model="gpt-4o-mini",
    )

    class _FakeResponses:
        def create(self, **kwargs):
            raise TimeoutError("ocr timed out")

    class _FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            self.responses = _FakeResponses()

    monkeypatch.setattr("markettrace.config.get_settings", lambda: settings)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    monkeypatch.setattr(
        statement_mod,
        "_render_pdf_ocr_chunks",
        lambda _, lines: [
            statement_mod._OcrImageChunk(
                transaction_lines=lines,
                image_url="data:image/png;base64,test-image",
            )
        ],
    )

    merchants = statement_mod._extract_openai_ocr_merchants_from_bytes(
        b"%PDF-1.7",
        text="26.05.26 »Î069 broken text 17,580",
        required=True,
    )

    assert merchants == [statement_mod._UNREADABLE_MERCHANT]


def test_parse_statement_text_warns_about_unreadable_ocr_merchants() -> None:
    statement = parse_statement_text(
        text="26.05.26 »Î069 broken text 17,580",
        file_name="statement.pdf",
        file_modified_at=datetime(2026, 6, 26, tzinfo=UTC),
        merchant_overrides=[statement_mod._UNREADABLE_MERCHANT],
    )

    assert "일부 가맹점명을 OCR로 읽지 못했습니다." in statement.warnings


def test_render_pdf_page_images_returns_png_data_urls() -> None:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "statement page")
    data = document.tobytes()
    document.close()

    images = statement_mod._render_pdf_page_images(data)

    assert len(images) == statement_mod._OPENAI_OCR_TABLE_VERTICAL_SPLITS
    assert all(image.startswith("data:image/png;base64,") for image in images)


def test_render_pdf_page_images_crops_transaction_table_area() -> None:
    import fitz

    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 72), "statement page")
    data = document.tobytes()
    document.close()

    image_url = statement_mod._render_pdf_page_images(data)[0]
    encoded = image_url.split(",", 1)[1]
    png_data = base64.b64decode(encoded)

    image_doc = fitz.open(stream=png_data, filetype="png")
    try:
        rendered_rect = image_doc.load_page(0).rect
    finally:
        image_doc.close()

    assert rendered_rect.width < 600 * statement_mod._OPENAI_OCR_RENDER_ZOOM
    assert rendered_rect.height < 800 * statement_mod._OPENAI_OCR_RENDER_ZOOM


def test_render_pdf_page_images_limits_to_statement_detail_pages() -> None:
    import fitz

    document = fitz.open()
    for page_number in range(4):
        page = document.new_page()
        page.insert_text((72, 72), f"statement page {page_number + 1}")
    data = document.tobytes()
    document.close()

    images = statement_mod._render_pdf_page_images(data)

    assert len(images) == 2 * statement_mod._OPENAI_OCR_TABLE_VERTICAL_SPLITS
    assert all(image.startswith("data:image/png;base64,") for image in images)


class _Settings:
    admin_username = "testadmin"
    admin_password = "testpass"
    auth_secret = "testsecret123"
    cors_allow_origins = "http://localhost:3000"
    card_statement_dir = "card_statement"
    card_statement_password = None
    ledger_ocr_provider = "auto"
    ledger_ocr_model = "gpt-4o-mini"
    openai_api_key = None

    @property
    def cors_origins_list(self) -> list[str]:
        return ["http://localhost:3000"]


@contextmanager
def _ledger_client(
    monkeypatch, settings: _Settings | None = None
) -> Iterator[tuple[TestClient, Session, _Settings]]:
    settings = settings or _Settings()
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: settings)
    monkeypatch.setattr(ledger_api, "get_settings", lambda: settings)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    app = create_app()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, session, settings
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _fake_statement() -> LedgerStatement:
    return LedgerStatement(
        file_name="statement.pdf",
        file_modified_at=datetime(2026, 6, 26, tzinfo=UTC),
        encrypted=True,
        payment_due_date=None,
        period_start=None,
        period_end=None,
        billed_total=None,
        domestic_total=None,
        foreign_total=None,
        parsed_total=1000,
        entry_count=1,
        entries=[
            LedgerEntry(
                date=datetime(2026, 6, 1, tzinfo=UTC).date(),
                card_tail="881",
                description="TEST MERCHANT",
                amount=1000,
                category="기타",
            )
        ],
        categories=[LedgerCategory(category="기타", amount=1000, count=1)],
        warnings=[],
    )


def test_ledger_statement_requires_auth(monkeypatch) -> None:
    with _ledger_client(monkeypatch) as (client, _, _):
        resp = client.post("/ledger/statement", json={"password": "pw"})

    assert resp.status_code == 401


def test_ledger_statement_returns_parsed_statement(monkeypatch) -> None:
    monkeypatch.setattr(ledger_api, "resolve_statement_dir", lambda _: SimpleNamespace())
    monkeypatch.setattr(ledger_api, "parse_latest_statement", lambda *_: _fake_statement())

    with _ledger_client(monkeypatch) as (client, session, _):
        token = create_token()
        resp = client.post(
            "/ledger/statement",
            json={"password": "pw"},
            headers={"Authorization": f"Bearer {token}"},
        )
        saved_count = session.query(LedgerStatementRecord).count()

    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 1
    assert data["entries"][0]["description"] == "TEST MERCHANT"
    assert data["statement_month"] == "2026-06-01"
    assert saved_count == 1


def test_ledger_statement_requires_statement_password(monkeypatch) -> None:
    monkeypatch.setattr(ledger_api, "resolve_statement_dir", lambda _: SimpleNamespace())

    def fail_parse_statement(*_) -> LedgerStatement:
        raise AssertionError("parser should not run without a statement password")

    monkeypatch.setattr(ledger_api, "parse_latest_statement", fail_parse_statement)

    with _ledger_client(monkeypatch) as (client, _, _):
        token = create_token()
        resp = client.post(
            "/ledger/statement",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "statement password required"


def test_ledger_statement_upload_requires_auth(monkeypatch) -> None:
    with _ledger_client(monkeypatch) as (client, _, _):
        resp = client.post(
            "/ledger/statement/upload",
            files={"file": ("statement.pdf", b"%PDF-1.7", "application/pdf")},
            data={"password": "pw"},
        )

    assert resp.status_code == 401


def test_ledger_statement_upload_requires_statement_password(monkeypatch) -> None:
    def fail_parse_statement_bytes(
        *, data: bytes, file_name: str, password: str | None
    ) -> LedgerStatement:
        raise AssertionError("parser should not run without a statement password")

    monkeypatch.setattr(ledger_api, "parse_statement_bytes", fail_parse_statement_bytes)

    with _ledger_client(monkeypatch) as (client, _, _):
        token = create_token()
        resp = client.post(
            "/ledger/statement/upload",
            files={"file": ("statement.pdf", b"%PDF-1.7", "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "statement password required"


def test_ledger_statement_upload_returns_parsed_statement(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_parse_statement_bytes(
        *, data: bytes, file_name: str, password: str | None
    ) -> LedgerStatement:
        seen["data"] = data
        seen["file_name"] = file_name
        seen["password"] = password
        return replace(_fake_statement(), file_name=file_name)

    async def fake_run_in_threadpool(func, *args, **kwargs):
        seen["threaded"] = True
        return func(*args, **kwargs)

    monkeypatch.setattr(ledger_api, "parse_statement_bytes", fake_parse_statement_bytes)
    monkeypatch.setattr(ledger_api, "run_in_threadpool", fake_run_in_threadpool)

    with _ledger_client(monkeypatch) as (client, session, _):
        token = create_token()
        resp = client.post(
            "/ledger/statement/upload",
            files={"file": ("uploaded.pdf", b"%PDF-1.7", "application/pdf")},
            data={"password": "pw"},
            headers={"Authorization": f"Bearer {token}"},
        )
        row = session.query(LedgerStatementRecord).one()
        saved_file_name = row.file_name
        saved_description = row.entries[0]["description"]

    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 1
    assert data["entries"][0]["description"] == "TEST MERCHANT"
    assert data["statement_month"] == "2026-06-01"
    assert data["uploaded_at"] is not None
    assert seen == {
        "data": b"%PDF-1.7",
        "file_name": "uploaded.pdf",
        "password": "pw",
        "threaded": True,
    }
    assert saved_file_name == "uploaded.pdf"
    assert saved_description == "TEST MERCHANT"


def test_ledger_statement_upload_uses_configured_password(monkeypatch) -> None:
    settings = _Settings()
    settings.card_statement_password = "configured-pw"

    seen: dict[str, object] = {}

    def fake_parse_statement_bytes(
        *, data: bytes, file_name: str, password: str | None
    ) -> LedgerStatement:
        seen["password"] = password
        return _fake_statement()

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(ledger_api, "parse_statement_bytes", fake_parse_statement_bytes)
    monkeypatch.setattr(ledger_api, "run_in_threadpool", fake_run_in_threadpool)

    with _ledger_client(monkeypatch, settings) as (client, _, _):
        token = create_token()
        resp = client.post(
            "/ledger/statement/upload",
            files={"file": ("uploaded.pdf", b"%PDF-1.7", "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert seen == {"password": "configured-pw"}


def test_ledger_statements_list_and_month_lookup(monkeypatch) -> None:
    monkeypatch.setattr(ledger_api, "parse_statement_bytes", lambda **_: _fake_statement())

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(ledger_api, "run_in_threadpool", fake_run_in_threadpool)

    with _ledger_client(monkeypatch) as (client, _, _):
        token = create_token()
        upload = client.post(
            "/ledger/statement/upload",
            files={"file": ("uploaded.pdf", b"%PDF-1.7", "application/pdf")},
            data={"password": "pw"},
            headers={"Authorization": f"Bearer {token}"},
        )
        summaries = client.get(
            "/ledger/statements", headers={"Authorization": f"Bearer {token}"}
        )
        detail = client.get(
            "/ledger/statements/2026-06",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert upload.status_code == 200
    assert summaries.status_code == 200
    assert summaries.json() == [
        {
            "statement_month": "2026-06-01",
            "file_name": "statement.pdf",
            "uploaded_at": upload.json()["uploaded_at"],
            "period_start": None,
            "period_end": None,
            "payment_due_date": None,
            "billed_total": None,
            "parsed_total": 1000,
            "entry_count": 1,
        }
    ]
    assert detail.status_code == 200
    assert detail.json()["entries"][0]["description"] == "TEST MERCHANT"


def test_saved_statement_detail_recategorizes_existing_entries(monkeypatch) -> None:
    with _ledger_client(monkeypatch) as (client, session, _):
        session.add(
            LedgerStatementRecord(
                statement_month=date(2026, 6, 1),
                file_name="saved.pdf",
                file_modified_at=datetime(2026, 6, 26, tzinfo=UTC),
                uploaded_at=datetime(2026, 6, 27, tzinfo=UTC),
                encrypted=True,
                payment_due_date=None,
                period_start=None,
                period_end=None,
                billed_total=None,
                domestic_total=None,
                foreign_total=None,
                parsed_total=10_500,
                entry_count=3,
                entries=[
                    {
                        "date": "2026-06-01",
                        "card_tail": "881",
                        "description": "스타벅스",
                        "amount": 3000,
                        "category": "기타",
                    },
                    {
                        "date": "2026-06-02",
                        "card_tail": "881",
                        "description": "쿠팡",
                        "amount": 7000,
                        "category": "기타",
                    },
                    {
                        "date": "2026-06-03",
                        "card_tail": "881",
                        "description": statement_mod._UNREADABLE_MERCHANT,
                        "amount": 500,
                        "category": "기타",
                    },
                ],
                categories=[{"category": "기타", "amount": 10_500, "count": 3}],
                warnings=[],
            )
        )
        session.commit()
        token = create_token()

        resp = client.get(
            "/ledger/statements/2026-06",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert [entry["category"] for entry in data["entries"]] == [
        "카페/간식",
        "온라인쇼핑",
        "인식불가",
    ]
    assert {category["category"] for category in data["categories"]} == {
        "카페/간식",
        "온라인쇼핑",
        "인식불가",
    }


def test_ledger_statement_upload_replaces_same_month(monkeypatch) -> None:
    first = _fake_statement()
    second = LedgerStatement(
        file_name="second.pdf",
        file_modified_at=datetime(2026, 6, 30, tzinfo=UTC),
        encrypted=True,
        payment_due_date=None,
        period_start=None,
        period_end=None,
        billed_total=None,
        domestic_total=None,
        foreign_total=None,
        parsed_total=2500,
        entry_count=1,
        entries=[
            LedgerEntry(
                date=date(2026, 6, 2),
                card_tail="123",
                description="SECOND MERCHANT",
                amount=2500,
                category="기타",
            )
        ],
        categories=[LedgerCategory(category="기타", amount=2500, count=1)],
        warnings=[],
    )
    statements = [first, second]

    def fake_parse_statement_bytes(**_) -> LedgerStatement:
        return statements.pop(0)

    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(ledger_api, "parse_statement_bytes", fake_parse_statement_bytes)
    monkeypatch.setattr(ledger_api, "run_in_threadpool", fake_run_in_threadpool)

    with _ledger_client(monkeypatch) as (client, session, _):
        token = create_token()
        for file_name in ("first.pdf", "second.pdf"):
            resp = client.post(
                "/ledger/statement/upload",
                files={"file": (file_name, b"%PDF-1.7", "application/pdf")},
                data={"password": "pw"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200

        rows = session.query(LedgerStatementRecord).all()
        saved_rows = [(row.file_name, row.parsed_total) for row in rows]

    assert saved_rows == [("second.pdf", 2500)]
