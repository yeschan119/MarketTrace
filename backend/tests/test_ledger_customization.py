"""Tests for the shared card / passbook category-customization layer."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.api.auth import create_token
from markettrace.api.deps import get_db
from markettrace.api.main import create_app
from markettrace.db.models import Base
from markettrace.ledger import customization as cx
from markettrace.ledger.customization import (
    CARD_DOMAIN,
    PASSBOOK_DOMAIN,
    CategoryResolver,
    CustomizationError,
)
from markettrace.ledger.fingerprint import make_entry_key
from markettrace.ledger.statements import (
    LedgerEntry,
    LedgerStatement,
)
from markettrace.ledger.storage import (
    aggregate_ledger_categories,
    build_ledger_statement_from_record,
    load_resolver,
    save_ledger_statement,
)
from markettrace.passbook.statements import (
    PassbookEntry,
    PassbookStatement,
)
from markettrace.passbook.storage import (
    build_passbook_statement_from_record,
    save_passbook_statement,
)

# --- fingerprint / resolver units ---------------------------------------------


def test_entry_key_stable_and_field_sensitive() -> None:
    a = LedgerEntry(
        date=date(2026, 6, 1), card_tail="881", description="STARBUCKS", amount=5000,
        category="카페/간식",
    )
    same = LedgerEntry(
        date=date(2026, 6, 1), card_tail="881", description="STARBUCKS", amount=5000,
        category="기타",  # category is not part of the identity
    )
    other = LedgerEntry(
        date=date(2026, 6, 1), card_tail="881", description="STARBUCKS", amount=5100,
        category="카페/간식",
    )
    assert a.entry_key == same.entry_key
    assert a.entry_key != other.entry_key


def test_resolver_precedence_override_then_rule_then_base() -> None:
    resolver = CategoryResolver(
        overrides={"k1": "업무경비"},
        rules=(("STARBUCKS", "간식비"),),
    )
    # override wins
    assert resolver.category_for(entry_key="k1", text="STARBUCKS", base_category="카페/간식") == "업무경비"
    # rule beats the built-in base
    assert resolver.category_for(entry_key="k2", text="STARBUCKS 강남", base_category="카페/간식") == "간식비"
    # no match falls back to the base
    assert resolver.category_for(entry_key="k3", text="UNKNOWN", base_category="기타") == "기타"


# --- storage-level CRUD -------------------------------------------------------


def test_set_and_clear_override(db_session: Session) -> None:
    cx.set_override(db_session, CARD_DOMAIN, entry_key="abc", category="여행")
    resolver = load_resolver(db_session, CARD_DOMAIN)
    assert resolver.overrides == {"abc": "여행"}

    # upsert updates in place, not duplicate
    cx.set_override(db_session, CARD_DOMAIN, entry_key="abc", category="휴가")
    assert load_resolver(db_session, CARD_DOMAIN).overrides == {"abc": "휴가"}

    assert cx.clear_override(db_session, CARD_DOMAIN, "abc") is True
    assert load_resolver(db_session, CARD_DOMAIN).overrides == {}
    assert cx.clear_override(db_session, CARD_DOMAIN, "abc") is False


def test_rule_upsert_and_normalization(db_session: Session) -> None:
    cx.create_rule(db_session, CARD_DOMAIN, keyword="스타 벅스", category="간식")
    cx.create_rule(db_session, CARD_DOMAIN, keyword="스타벅스", category="카페")  # same norm
    rules = cx.list_rules(db_session, CARD_DOMAIN)
    assert len(rules) == 1
    assert rules[0].category == "카페"


def test_rule_and_override_are_domain_scoped(db_session: Session) -> None:
    cx.set_override(db_session, CARD_DOMAIN, entry_key="k", category="카드전용")
    assert load_resolver(db_session, PASSBOOK_DOMAIN).overrides == {}
    assert load_resolver(db_session, CARD_DOMAIN).overrides == {"k": "카드전용"}


def test_empty_values_rejected(db_session: Session) -> None:
    with pytest.raises(CustomizationError):
        cx.set_override(db_session, CARD_DOMAIN, entry_key="k", category="  ")
    with pytest.raises(CustomizationError):
        cx.create_rule(db_session, CARD_DOMAIN, keyword="", category="x")
    with pytest.raises(CustomizationError):
        cx.create_rule(db_session, CARD_DOMAIN, keyword="...", category="x")


def test_available_categories_lists_builtin_and_custom(db_session: Session) -> None:
    cx.create_custom_category(db_session, CARD_DOMAIN, name="여행경비")
    cx.create_rule(db_session, CARD_DOMAIN, keyword="AAA", category="규칙카테고리")
    cx.set_override(db_session, CARD_DOMAIN, entry_key="k", category="오버라이드카테고리")

    names = [c.name for c in cx.available_categories(db_session, CARD_DOMAIN)]
    assert "카페/간식" in names  # a built-in
    assert {"여행경비", "규칙카테고리", "오버라이드카테고리"} <= set(names)
    # no duplicates
    assert len(names) == len(set(names))


def test_delete_custom_category_cascades(db_session: Session) -> None:
    cx.create_custom_category(db_session, CARD_DOMAIN, name="여행")
    cx.create_rule(db_session, CARD_DOMAIN, keyword="AGODA", category="여행")
    cx.set_override(db_session, CARD_DOMAIN, entry_key="k", category="여행")

    assert cx.delete_custom_category(db_session, CARD_DOMAIN, "여행") is True
    assert cx.list_rules(db_session, CARD_DOMAIN) == []
    assert cx.list_overrides(db_session, CARD_DOMAIN) == []
    assert [c.name for c in cx.list_custom_categories(db_session, CARD_DOMAIN)] == []


def test_delete_category_that_only_exists_via_override(db_session: Session) -> None:
    # A category referenced only by an override (never explicitly created) must
    # still be deletable, cascading the override away.
    cx.set_override(db_session, CARD_DOMAIN, entry_key="k", category="임시분류")
    assert "임시분류" in {c.name for c in cx.available_categories(db_session, CARD_DOMAIN)}
    assert cx.delete_custom_category(db_session, CARD_DOMAIN, "임시분류") is True
    assert cx.list_overrides(db_session, CARD_DOMAIN) == []
    assert cx.delete_custom_category(db_session, CARD_DOMAIN, "임시분류") is False


# --- end-to-end through a saved statement -------------------------------------


def _card_statement(entries: list[LedgerEntry]) -> LedgerStatement:
    return LedgerStatement(
        file_name="s.pdf",
        file_modified_at=datetime(2026, 6, 26, tzinfo=UTC),
        encrypted=True,
        payment_due_date=None,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        billed_total=None,
        domestic_total=None,
        foreign_total=None,
        parsed_total=sum(e.amount for e in entries),
        entry_count=len(entries),
        entries=entries,
        categories=[],
        warnings=[],
    )


def test_override_reclassifies_saved_card_entry(db_session: Session) -> None:
    entry = LedgerEntry(
        date=date(2026, 6, 10), card_tail="881", description="STARBUCKS", amount=5000,
        category="카페/간식",
    )
    row = save_ledger_statement(db_session, _card_statement([entry]))

    # baseline: built-in classifies STARBUCKS as 카페/간식
    baseline = build_ledger_statement_from_record(row, load_resolver(db_session, CARD_DOMAIN))
    assert baseline.entries[0].category == "카페/간식"

    cx.set_override(db_session, CARD_DOMAIN, entry_key=entry.entry_key, category="업무경비")
    after = build_ledger_statement_from_record(row, load_resolver(db_session, CARD_DOMAIN))
    assert after.entries[0].category == "업무경비"
    # aggregation reflects the override too
    totals = {c.category: c.amount for c in aggregate_ledger_categories(
        db_session, month=date(2026, 6, 1), window="month"
    )}
    assert totals == {"업무경비": 5000}


def test_rule_reclassifies_all_matching_card_entries(db_session: Session) -> None:
    entries = [
        LedgerEntry(date=date(2026, 6, 1), card_tail="1", description="STARBUCKS A", amount=4000, category="카페/간식"),
        LedgerEntry(date=date(2026, 6, 2), card_tail="1", description="STARBUCKS B", amount=6000, category="카페/간식"),
        LedgerEntry(date=date(2026, 6, 3), card_tail="1", description="GS25", amount=3000, category="편의점"),
    ]
    save_ledger_statement(db_session, _card_statement(entries))
    cx.create_rule(db_session, CARD_DOMAIN, keyword="STARBUCKS", category="회의비")

    totals = {c.category: c.amount for c in aggregate_ledger_categories(
        db_session, month=date(2026, 6, 1), window="month"
    )}
    assert totals["회의비"] == 10000
    assert totals["편의점"] == 3000
    assert "카페/간식" not in totals


def test_override_reclassifies_saved_passbook_entry(db_session: Session) -> None:
    entry = PassbookEntry(
        date=date(2026, 6, 10), time="12:00", summary="타행이체", direction="out",
        amount=50000, withdrawal=50000, deposit=0, description="홍길동", balance=100000,
        branch="강남", category="타행이체",
    )
    statement = PassbookStatement(
        file_name="p.pdf", file_modified_at=datetime(2026, 6, 26, tzinfo=UTC),
        encrypted=True, account_no=None, account_holder=None,
        period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
        closing_balance=100000, withdrawal_total=50000, deposit_total=0,
        entry_count=1, entries=[entry], categories=[], warnings=[],
    )
    row = save_passbook_statement(db_session, statement)
    cx.set_override(db_session, PASSBOOK_DOMAIN, entry_key=entry.entry_key, category="월세")

    from markettrace.passbook.storage import load_resolver as pb_resolver

    after = build_passbook_statement_from_record(row, pb_resolver(db_session, PASSBOOK_DOMAIN))
    assert after.entries[0].category == "월세"


# --- API round-trip -----------------------------------------------------------


class _AuthSettings:
    auth_secret = "testsecret123"


@pytest.fixture
def client(monkeypatch) -> Iterator[tuple[TestClient, Session]]:
    settings = _AuthSettings()
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: settings)

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
        with TestClient(app) as test_client:
            yield test_client, session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_customization_requires_auth(client) -> None:
    test_client, _ = client
    assert test_client.get("/ledger/customization").status_code == 401
    assert test_client.get("/passbook/customization").status_code == 401


def test_customization_api_round_trip(client) -> None:
    test_client, _ = client
    headers = {"Authorization": f"Bearer {create_token()}"}

    # create a category
    resp = test_client.post(
        "/ledger/customization/category", json={"name": "회의비"}, headers=headers
    )
    assert resp.status_code == 200
    assert any(c["name"] == "회의비" for c in resp.json()["available_categories"])

    # create a rule
    resp = test_client.post(
        "/ledger/customization/rule",
        json={"keyword": "STARBUCKS", "category": "회의비"},
        headers=headers,
    )
    assert resp.status_code == 200
    rules = resp.json()["rules"]
    assert len(rules) == 1
    rule_id = rules[0]["id"]

    # set an override
    key = make_entry_key(["2026-06-01", "881", "TEST", 1000])
    resp = test_client.put(
        "/ledger/customization/override",
        json={"entry_key": key, "category": "회의비", "description": "TEST"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["overrides"][0]["entry_key"] == key

    # clear the override
    resp = test_client.put(
        "/ledger/customization/override",
        json={"entry_key": key, "category": None},
        headers=headers,
    )
    assert resp.json()["overrides"] == []

    # delete the rule
    resp = test_client.delete(
        f"/ledger/customization/rule/{rule_id}", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["rules"] == []

    # passbook domain is isolated
    resp = test_client.get("/passbook/customization", headers=headers)
    assert resp.json()["rules"] == []
    assert not any(c["name"] == "회의비" for c in resp.json()["available_categories"])
