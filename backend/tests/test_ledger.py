"""Tests for card-statement ledger parsing and API auth gating."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import markettrace.api.ledger as ledger_api
import markettrace.ledger.statements as statement_mod
from markettrace.api.auth import create_token
from markettrace.api.main import create_app
from markettrace.ledger.statements import (
    LedgerCategory,
    LedgerEntry,
    LedgerStatement,
    StatementError,
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
        "식비/마트",
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
    assert statement.warnings == [
        "청구금액과 파싱 거래 합계가 다릅니다. 할부, 수수료, 할인, 중복 상세 내역을 확인하세요."
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
            return SimpleNamespace(output_text='{"merchants":["지에스더프레시","케이에프씨"]}')

    class _FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            seen["api_key"] = api_key
            self.responses = _FakeResponses()

    fake_openai = SimpleNamespace(OpenAI=_FakeOpenAI)
    monkeypatch.setattr("markettrace.config.get_settings", lambda: settings)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setattr(
        statement_mod,
        "_render_pdf_page_images",
        lambda _: ["data:image/png;base64,test-image"],
    )

    merchants = statement_mod._extract_openai_ocr_merchants_from_bytes(
        b"%PDF-1.7",
        text="\n".join(
            [
                "26.05.26 »Î069 broken text 17,580",
                "26.06.09 »Î881 broken text 11,500",
            ]
        ),
    )

    assert merchants == ["지에스더프레시", "케이에프씨"]
    assert seen["api_key"] == "test-key"
    assert seen["model"] == "gpt-4o-mini"
    assert seen["max_output_tokens"] == 2000
    assert seen["timeout"] == statement_mod._OPENAI_OCR_TIMEOUT_SECONDS
    request = seen["input"][0]["content"]
    assert request[0]["type"] == "input_text"
    assert request[1] == {
        "type": "input_image",
        "image_url": "data:image/png;base64,test-image",
        "detail": "high",
    }


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


def test_required_openai_ocr_fails_instead_of_returning_broken_text(monkeypatch) -> None:
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
        "_render_pdf_page_images",
        lambda _: ["data:image/png;base64,test-image"],
    )
    monkeypatch.setattr(
        statement_mod,
        "_call_openai_merchant_ocr",
        lambda *_, **__: '{"merchants":[]}',
    )

    with pytest.raises(StatementError):
        statement_mod._extract_ocr_merchants_from_bytes(
            b"raw-pdf",
            None,
            text="26.05.26 garbled merchant text 5,000",
            file_name="statement.pdf",
        )


def test_render_pdf_page_images_returns_png_data_urls() -> None:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "statement page")
    data = document.tobytes()
    document.close()

    images = statement_mod._render_pdf_page_images(data)

    assert len(images) == 1
    assert images[0].startswith("data:image/png;base64,")


def test_render_pdf_page_images_limits_to_statement_detail_pages() -> None:
    import fitz

    document = fitz.open()
    for page_number in range(4):
        page = document.new_page()
        page.insert_text((72, 72), f"statement page {page_number + 1}")
    data = document.tobytes()
    document.close()

    images = statement_mod._render_pdf_page_images(data)

    assert len(images) == 2
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
    settings = _Settings()
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: settings)
    monkeypatch.setattr(ledger_api, "get_settings", lambda: settings)
    app = create_app()

    with TestClient(app) as client:
        resp = client.post("/ledger/statement", json={"password": "pw"})

    assert resp.status_code == 401


def test_ledger_statement_returns_parsed_statement(monkeypatch) -> None:
    settings = _Settings()
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: settings)
    monkeypatch.setattr(ledger_api, "get_settings", lambda: settings)
    monkeypatch.setattr(ledger_api, "resolve_statement_dir", lambda _: SimpleNamespace())
    monkeypatch.setattr(ledger_api, "parse_latest_statement", lambda *_: _fake_statement())

    token = create_token()
    app = create_app()

    with TestClient(app) as client:
        resp = client.post(
            "/ledger/statement",
            json={"password": "pw"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 1
    assert data["entries"][0]["description"] == "TEST MERCHANT"


def test_ledger_statement_upload_requires_auth(monkeypatch) -> None:
    settings = _Settings()
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: settings)
    monkeypatch.setattr(ledger_api, "get_settings", lambda: settings)
    app = create_app()

    with TestClient(app) as client:
        resp = client.post(
            "/ledger/statement/upload",
            files={"file": ("statement.pdf", b"%PDF-1.7", "application/pdf")},
            data={"password": "pw"},
        )

    assert resp.status_code == 401


def test_ledger_statement_upload_returns_parsed_statement(monkeypatch) -> None:
    settings = _Settings()
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: settings)
    monkeypatch.setattr(ledger_api, "get_settings", lambda: settings)

    seen: dict[str, object] = {}

    def fake_parse_statement_bytes(
        *, data: bytes, file_name: str, password: str | None
    ) -> LedgerStatement:
        seen["data"] = data
        seen["file_name"] = file_name
        seen["password"] = password
        return _fake_statement()

    async def fake_run_in_threadpool(func, *args, **kwargs):
        seen["threaded"] = True
        return func(*args, **kwargs)

    monkeypatch.setattr(ledger_api, "parse_statement_bytes", fake_parse_statement_bytes)
    monkeypatch.setattr(ledger_api, "run_in_threadpool", fake_run_in_threadpool)

    token = create_token()
    app = create_app()

    with TestClient(app) as client:
        resp = client.post(
            "/ledger/statement/upload",
            files={"file": ("uploaded.pdf", b"%PDF-1.7", "application/pdf")},
            data={"password": "pw"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 1
    assert data["entries"][0]["description"] == "TEST MERCHANT"
    assert seen == {
        "data": b"%PDF-1.7",
        "file_name": "uploaded.pdf",
        "password": "pw",
        "threaded": True,
    }
