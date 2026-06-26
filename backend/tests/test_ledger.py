"""Tests for card-statement ledger parsing and API auth gating."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

import markettrace.api.ledger as ledger_api
from markettrace.api.auth import create_token
from markettrace.api.main import create_app
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
        "식비/마트",
        "구독/디지털",
    }


class _Settings:
    admin_username = "testadmin"
    admin_password = "testpass"
    auth_secret = "testsecret123"
    cors_allow_origins = "http://localhost:3000"
    card_statement_dir = "card_statement"
    card_statement_password = None

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

    monkeypatch.setattr(ledger_api, "parse_statement_bytes", fake_parse_statement_bytes)

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
    }
