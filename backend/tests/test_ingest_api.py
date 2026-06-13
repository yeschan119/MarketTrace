"""Tests for POST /ingest API endpoint: auth gating, 202 response, and idempotency."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from markettrace.api.auth import create_token
from markettrace.api.ingest import _DEMO_FILINGS, _ingest_one
from markettrace.api.main import create_app
from markettrace.db.models import Base, Document


class _Settings:
    admin_username = "testadmin"
    admin_password = "testpass"
    auth_secret = "testsecret123"
    cors_allow_origins = "http://localhost:3000"
    kr_market_index_ticker = "069500"
    sec_user_agent = "test agent@example.com"

    @property
    def cors_origins_list(self) -> list[str]:
        return ["http://localhost:3000"]


@pytest.fixture
def fake_settings() -> _Settings:
    return _Settings()


@pytest.fixture
def ingest_client(monkeypatch, fake_settings: _Settings) -> TestClient:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: fake_settings)
    monkeypatch.setattr("markettrace.api.main.get_settings", lambda: fake_settings)
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def valid_token(monkeypatch, fake_settings: _Settings) -> str:
    monkeypatch.setattr("markettrace.api.auth.get_settings", lambda: fake_settings)
    return create_token()


# ---------------------------------------------------------------------------
# POST /ingest — auth gating
# ---------------------------------------------------------------------------


def test_ingest_no_auth_header(ingest_client: TestClient) -> None:
    resp = ingest_client.post("/ingest")
    assert resp.status_code == 401


def test_ingest_invalid_token(ingest_client: TestClient) -> None:
    resp = ingest_client.post("/ingest", headers={"Authorization": "Bearer notavalidtoken"})
    assert resp.status_code == 401


def test_ingest_valid_token_returns_202(
    monkeypatch, ingest_client: TestClient, valid_token: str
) -> None:
    called: list[bool] = []

    def _fake_ingest() -> None:
        called.append(True)

    monkeypatch.setattr("markettrace.api.ingest.run_demo_ingest", _fake_ingest)
    resp = ingest_client.post("/ingest", headers={"Authorization": f"Bearer {valid_token}"})
    assert resp.status_code == 202
    assert resp.json() == {"status": "started"}
    assert called, "background ingest task was not scheduled/invoked"


# ---------------------------------------------------------------------------
# _ingest_one idempotency (unit test — no network)
# ---------------------------------------------------------------------------


@pytest.fixture
def mem_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_ingest_one_skips_existing(monkeypatch, mem_session, fake_settings: _Settings) -> None:
    """_ingest_one must not call run_slice when the document already exists in the DB."""
    filing = _DEMO_FILINGS[0]  # US / AAPL
    source = "sec"
    accession = filing["accession"]

    doc = Document(
        source=source,
        external_id=accession,
        url="https://example.com",
        title="seed",
        content_hash="seedhash_abc123",
        market="US",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    mem_session.add(doc)
    mem_session.commit()

    fake_ref = SimpleNamespace(source=source, external_id=accession)

    class _FakeDisclosure:
        def list_for_issuer(self, issuer_id, from_date, primary_ticker=None):
            return [fake_ref]

    monkeypatch.setattr(
        "markettrace.api.ingest.get_disclosure_provider",
        lambda *a, **kw: _FakeDisclosure(),
    )
    monkeypatch.setattr("markettrace.api.ingest.get_price_provider", lambda *a: object())

    run_slice_calls: list[bool] = []
    monkeypatch.setattr(
        "markettrace.api.ingest.run_slice",
        lambda *a, **kw: run_slice_calls.append(True),
    )

    _ingest_one(mem_session, None, fake_settings, filing)

    assert not run_slice_calls, "run_slice must not be called for an already-ingested document"
