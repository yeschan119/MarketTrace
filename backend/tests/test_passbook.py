"""Tests for bank-account (passbook) parsing, storage, and API auth gating."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import markettrace.api.passbook as passbook_api
from markettrace.api.auth import create_token
from markettrace.api.deps import get_db
from markettrace.api.main import create_app
from markettrace.db.models import Base, PassbookStatementRecord
from markettrace.passbook.statements import (
    PassbookEntry,
    PassbookStatement,
    categorize_summary,
    parse_passbook_text,
)
from markettrace.passbook.storage import (
    aggregate_passbook_categories,
    save_passbook_statement,
    top_passbook_entries,
)


def _sample_passbook_text() -> str:
    """A trimmed Shinhan transaction export, including PDF line wraps."""
    return """거래내역조회
계좌번호 [신한] 110-***-*09683 성명 강*찬
조회기간 2026.05.29 ~ 2026.06.29 대출한도
출금가능금액 3,125,067원 미결제타점권
총잔액 3,125,067원 지급제한금액
거래일자 거래시간 적요 출금(원) 입금(원) 내용 잔액(원) 거래점
ⓒ SHINHAN BANK. All rights reserved.
* 본 명세는 단순 참고용으로만 사용될 수 있습니다.
20260629 13:04:42 인터넷뱅킹 0 34,415 우아한청년들 3,125,067 (우리)
20260628 19:10:17 효성CD 0 148,500 강응찬 3,090,652 디금융
20260627 20:10:48 펌뱅킹 이체 20,000 0 네이버페이충전 2,942,152 분당중
20260624 08:43:26 모바일 147,520 0 디엠씨(DMC)해
링 1,914,152 디금융
20260618 15:56:06 타행모바일
뱅킹 0 70,000 강응찬 4,705,784 (카카)
20260620 04:33:15 이자 0 617 03.21~06.19 4,493,401 디금융
20260601 18:01:23 카드결제 2,485,198 0 신한카드 2,085,348 원신한
20260601 07:03:19 의보 22,600 0 2605국민건강 4,570,546 디금융
"""


def test_parse_passbook_text_extracts_summary_and_entries() -> None:
    statement = parse_passbook_text(
        text=_sample_passbook_text(),
        file_name="passbook.pdf",
        file_modified_at=datetime(2026, 6, 29, tzinfo=UTC),
        encrypted=True,
    )

    assert statement.encrypted is True
    assert statement.account_no == "110-***-*09683"
    assert statement.account_holder == "강*찬"
    assert statement.period_start.isoformat() == "2026-05-29"
    assert statement.period_end.isoformat() == "2026-06-29"
    assert statement.closing_balance == 3_125_067
    assert statement.entry_count == 8
    assert statement.withdrawal_total == 20_000 + 147_520 + 2_485_198 + 22_600
    assert statement.deposit_total == 34_415 + 148_500 + 70_000 + 617


def test_parse_passbook_text_reassembles_wrapped_rows() -> None:
    statement = parse_passbook_text(
        text=_sample_passbook_text(),
        file_name="passbook.pdf",
        file_modified_at=datetime(2026, 6, 29, tzinfo=UTC),
    )
    by_amount = {entry.amount: entry for entry in statement.entries}

    # 내용 wrapped across two lines: "디엠씨(DMC)해" + "링".
    wrapped_desc = by_amount[147_520]
    assert wrapped_desc.summary == "모바일"
    assert wrapped_desc.description == "디엠씨(DMC)해링"
    assert wrapped_desc.balance == 1_914_152
    assert wrapped_desc.branch == "디금융"

    # 적요 wrapped across two lines: "타행모바일" + "뱅킹".
    wrapped_summary = by_amount[70_000]
    assert wrapped_summary.summary == "타행모바일뱅킹"
    assert wrapped_summary.category == "타행이체"
    assert wrapped_summary.direction == "in"


def test_parse_passbook_text_splits_withdrawal_and_deposit() -> None:
    statement = parse_passbook_text(
        text=_sample_passbook_text(),
        file_name="passbook.pdf",
        file_modified_at=datetime(2026, 6, 29, tzinfo=UTC),
    )
    by_amount = {entry.amount: entry for entry in statement.entries}

    card = by_amount[2_485_198]
    assert card.direction == "out"
    assert card.withdrawal == 2_485_198
    assert card.deposit == 0
    assert card.category == "카드결제"

    deposit = by_amount[34_415]
    assert deposit.direction == "in"
    assert deposit.withdrawal == 0
    assert deposit.deposit == 34_415

    # 내용 that begins with digits ("2605국민건강") must not be mistaken for amounts.
    health = by_amount[22_600]
    assert health.description == "2605국민건강"
    assert health.balance == 4_570_546
    assert health.category == "공과금/세금"

    # 내용 holding a date-like token ("03.21~06.19") keeps its 잔액 separate.
    interest = by_amount[617]
    assert interest.description == "03.21~06.19"
    assert interest.balance == 4_493_401
    assert interest.category == "이자"


def test_categorize_summary_groups_and_falls_back() -> None:
    assert categorize_summary("신한카드") == "카드결제"
    assert categorize_summary("타행인터넷뱅킹") == "타행이체"
    assert categorize_summary("펌뱅킹 이체") == "펌뱅킹"
    assert categorize_summary("효성CD") == "ATM/CD"
    assert categorize_summary("이자") == "이자"
    # An unmapped 적요 keeps its cleaned label.
    assert categorize_summary("배당금  입금") == "배당금 입금"
    assert categorize_summary("") == "기타"


def _entry(
    *,
    day: int,
    summary: str,
    withdrawal: int = 0,
    deposit: int = 0,
    description: str = "x",
) -> PassbookEntry:
    direction = "out" if withdrawal > 0 else "in"
    return PassbookEntry(
        date=date(2026, 6, day),
        time="12:00:00",
        summary=summary,
        direction=direction,
        amount=withdrawal if withdrawal else deposit,
        withdrawal=withdrawal,
        deposit=deposit,
        description=description,
        balance=None,
        branch="",
        category=categorize_summary(summary),
    )


def _fake_statement() -> PassbookStatement:
    entries = [
        _entry(day=1, summary="카드결제", withdrawal=2_000_000, description="신한카드"),
        _entry(day=2, summary="펌뱅킹 이체", withdrawal=20_000, description="네이버페이충전"),
        _entry(day=3, summary="인터넷뱅킹", deposit=34_415, description="우아한청년들"),
        _entry(day=4, summary="타행이체", deposit=2_555_080, description="홍성혜"),
    ]
    return PassbookStatement(
        file_name="passbook.pdf",
        file_modified_at=datetime(2026, 6, 29, tzinfo=UTC),
        encrypted=True,
        account_no="110-***-*09683",
        account_holder="강*찬",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 29),
        closing_balance=3_125_067,
        withdrawal_total=2_020_000,
        deposit_total=2_589_495,
        entry_count=len(entries),
        entries=entries,
        categories=[],
        warnings=[],
    )


def _memory_session() -> tuple[Session, object]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory(), engine


def test_storage_round_trip_aggregates_and_ranks() -> None:
    session, engine = _memory_session()
    try:
        save_passbook_statement(session, _fake_statement())
        anchor = date(2026, 6, 1)

        categories = aggregate_passbook_categories(session, month=anchor, window="month")
        totals = {c.category: (c.withdrawal, c.deposit) for c in categories}
        assert totals["카드결제"] == (2_000_000, 0)
        assert totals["타행이체"] == (0, 2_555_080)

        top_out = top_passbook_entries(
            session, month=anchor, window="month", direction="out"
        )
        assert [e.withdrawal for e in top_out] == [2_000_000, 20_000]

        top_in = top_passbook_entries(
            session, month=anchor, window="month", direction="in"
        )
        assert [e.deposit for e in top_in] == [2_555_080, 34_415]
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


class _Settings:
    admin_username = "testadmin"
    admin_password = "testpass"
    auth_secret = "testsecret123"
    cors_allow_origins = "http://localhost:3000"
    passbook_dir = "passbook"
    passbook_password = None

    @property
    def cors_origins_list(self) -> list[str]:
        return ["http://localhost:3000"]


@contextmanager
def _passbook_client(
    monkeypatch, settings: _Settings | None = None
) -> Iterator[tuple[TestClient, Session, _Settings]]:
    settings = settings or _Settings()
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: settings)
    monkeypatch.setattr(passbook_api, "get_settings", lambda: settings)

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


def test_passbook_statement_requires_auth(monkeypatch) -> None:
    with _passbook_client(monkeypatch) as (client, _, _):
        resp = client.post("/passbook/statement", json={"password": "pw"})

    assert resp.status_code == 401


def test_passbook_statement_returns_parsed_statement(monkeypatch) -> None:
    monkeypatch.setattr(passbook_api, "resolve_passbook_dir", lambda _: SimpleNamespace())
    monkeypatch.setattr(passbook_api, "parse_latest_passbook", lambda *_: _fake_statement())

    with _passbook_client(monkeypatch) as (client, session, _):
        token = create_token()
        resp = client.post(
            "/passbook/statement",
            json={"password": "pw"},
            headers={"Authorization": f"Bearer {token}"},
        )
        saved_count = session.query(PassbookStatementRecord).count()

    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_count"] == 4
    assert data["account_no"] == "110-***-*09683"
    assert data["withdrawal_total"] == 2_020_000
    assert data["deposit_total"] == 2_589_495
    assert data["statement_month"] == "2026-06-01"
    assert saved_count == 1


def test_passbook_upload_round_trips_through_storage(monkeypatch) -> None:
    monkeypatch.setattr(
        passbook_api, "parse_passbook_bytes", lambda **_: _fake_statement()
    )

    with _passbook_client(monkeypatch) as (client, _, _):
        token = create_token()
        resp = client.post(
            "/passbook/statement/upload",
            files={"file": ("passbook.pdf", b"%PDF-1.7 fake", "application/pdf")},
            data={"password": "pw"},
            headers={"Authorization": f"Bearer {token}"},
        )
        list_resp = client.get(
            "/passbook/statements", headers={"Authorization": f"Bearer {token}"}
        )
        categories_resp = client.get(
            "/passbook/categories?month=2026-06&window=month",
            headers={"Authorization": f"Bearer {token}"},
        )
        top_resp = client.get(
            "/passbook/entries/top?month=2026-06&window=month&direction=in",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert [s["statement_month"] for s in list_resp.json()] == ["2026-06-01"]
    category_names = {c["category"] for c in categories_resp.json()}
    assert {"카드결제", "타행이체"} <= category_names
    assert top_resp.json()[0]["deposit"] == 2_555_080
