"""Tests for GET /instruments — the review picker's instrument list."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.api.deps import get_db
from markettrace.api.main import create_app
from markettrace.db.models import Base, Instrument


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    s = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(session) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded(session: Session) -> None:
    session.add_all(
        [
            Instrument(market="KR", ticker="005930", name="Samsung Electronics", industry="Tech"),
            Instrument(market="KR", ticker="000660", name="SK hynix", industry="Tech"),
            Instrument(market="US", ticker="AAPL", name="Apple Inc.", industry="Tech"),
        ]
    )
    session.commit()


def test_list_all_sorted_by_market_then_ticker(client: TestClient, seeded: None) -> None:
    resp = client.get("/instruments")
    assert resp.status_code == 200
    rows = resp.json()
    assert [(r["market"], r["ticker"]) for r in rows] == [
        ("KR", "000660"),
        ("KR", "005930"),
        ("US", "AAPL"),
    ]
    assert rows[0]["name"] == "SK hynix"
    assert rows[0]["industry"] == "Tech"


def test_query_filters_ticker_and_name_substring(client: TestClient, seeded: None) -> None:
    # ticker substring
    tickers = [r["ticker"] for r in client.get("/instruments?q=0066").json()]
    assert tickers == ["000660"]
    # name substring, case-insensitive
    names = [r["name"] for r in client.get("/instruments?q=apple").json()]
    assert names == ["Apple Inc."]


def test_market_filter(client: TestClient, seeded: None) -> None:
    rows = client.get("/instruments?market=US").json()
    assert [r["ticker"] for r in rows] == ["AAPL"]


def test_empty_when_no_match(client: TestClient, seeded: None) -> None:
    assert client.get("/instruments?q=zzzz").json() == []
