"""Tests for POST /ingest API endpoint: auth gating, 202 response, and idempotency."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import markettrace.api.ingest as ingest_mod
from markettrace.api.auth import create_token
from markettrace.api.ingest import (
    _DEMO_FILINGS,
    _ingest_corpus_kr,
    _ingest_corpus_us,
    _ingest_macro,
    _ingest_one,
    _ingest_requested_instrument,
    _ingest_summary,
    main,
)
from markettrace.api.main import create_app
from markettrace.api.schemas import InstrumentAnalyzeRequest
from markettrace.db.models import Base, Document, Event, Instrument
from markettrace.providers.base import IssuerResolution


class _Settings:
    admin_username = "testadmin"
    admin_password = "testpass"
    auth_secret = "testsecret123"
    cors_allow_origins = "http://localhost:3000"
    kr_market_index_ticker = "069500"
    sec_user_agent = "test agent@example.com"
    opendart_api_key = "testkey"

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
    monkeypatch.setattr("markettrace.api.ingest.get_settings", lambda: fake_settings)
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


def test_ingest_wait_runs_foreground_and_returns_summary(
    monkeypatch, ingest_client: TestClient, valid_token: str
) -> None:
    called: list[bool] = []

    monkeypatch.setattr("markettrace.api.ingest.run_demo_ingest", lambda: called.append(True))
    monkeypatch.setattr(
        "markettrace.api.ingest._load_ingest_summary",
        lambda: {"documents": 2, "events": 3, "events_by_ticker": {"AAPL": 3}},
    )

    resp = ingest_client.post(
        "/ingest?wait=true",
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "completed",
        "summary": {"documents": 2, "events": 3, "events_by_ticker": {"AAPL": 3}},
    }
    assert called == [True]


def test_analyze_instrument_no_auth_header(ingest_client: TestClient) -> None:
    resp = ingest_client.post(
        "/instruments/analyze",
        json={"market": "US", "ticker": "AAPL"},
    )
    assert resp.status_code == 401


def test_analyze_instrument_valid_token_schedules_background_task(
    monkeypatch, ingest_client: TestClient, valid_token: str
) -> None:
    requests: list[InstrumentAnalyzeRequest] = []
    monkeypatch.setattr(ingest_mod, "run_instrument_ingest", requests.append)

    class _Disclosure:
        def resolve_issuer(self, query):
            assert query == "AAPL"
            return IssuerResolution("0000320193", "AAPL", "Apple Inc.")

    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: _Disclosure())

    resp = ingest_client.post(
        "/instruments/analyze",
        json={"market": "us", "ticker": "aapl", "name": "Apple Inc."},
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert resp.status_code == 202
    assert resp.json() == {
        "status": "started",
        "market": "US",
        "ticker": "AAPL",
        "max_filings": 10,
    }
    assert len(requests) == 1
    assert requests[0].market == "US"
    assert requests[0].ticker == "AAPL"


def test_analyze_instrument_normalizes_short_kr_ticker(
    monkeypatch, ingest_client: TestClient, valid_token: str
) -> None:
    requests: list[InstrumentAnalyzeRequest] = []
    monkeypatch.setattr(ingest_mod, "run_instrument_ingest", requests.append)

    class _Disclosure:
        def resolve_issuer(self, query):
            assert query == "005930"
            return IssuerResolution("00126380", "005930", "삼성전자")

    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: _Disclosure())

    resp = ingest_client.post(
        "/instruments/analyze",
        json={"market": "KR", "ticker": "5930", "max_filings": 3},
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert resp.status_code == 202
    assert resp.json()["ticker"] == "005930"
    assert requests[0].ticker == "005930"


def test_analyze_instrument_company_name_only_resolves_ticker(
    monkeypatch, ingest_client: TestClient, valid_token: str
) -> None:
    requests: list[InstrumentAnalyzeRequest] = []
    monkeypatch.setattr(ingest_mod, "run_instrument_ingest", requests.append)

    class _Disclosure:
        def resolve_issuer(self, query):
            assert query == "삼성전자"
            return IssuerResolution("00126380", "005930", "삼성전자")

    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: _Disclosure())

    resp = ingest_client.post(
        "/instruments/analyze",
        json={"market": "KR", "name": "삼성전자"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert resp.status_code == 202
    assert resp.json()["ticker"] == "005930"
    assert requests[0].ticker == "005930"
    assert requests[0].name == "삼성전자"


def test_analyze_instrument_unknown_company_returns_404(
    monkeypatch, ingest_client: TestClient, valid_token: str
) -> None:
    monkeypatch.setattr(ingest_mod, "run_instrument_ingest", lambda request: None)

    class _Disclosure:
        def resolve_issuer(self, query):
            return None

    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: _Disclosure())

    resp = ingest_client.post(
        "/instruments/analyze",
        json={"market": "US", "name": "definitely unknown issuer"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert resp.status_code == 404


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


# ---------------------------------------------------------------------------
# _ingest_macro — gated on FRED_API_KEY (unit test — no network)
# ---------------------------------------------------------------------------


def test_ingest_macro_skips_without_key(monkeypatch) -> None:
    """No FRED_API_KEY -> macro ingest is a no-op (never builds a provider)."""
    settings = SimpleNamespace(fred_api_key=None, macro_series_list=["CPIAUCSL"])

    provider_calls: list[bool] = []
    monkeypatch.setattr(
        "markettrace.providers.registry.get_macro_provider",
        lambda *a, **kw: provider_calls.append(True),
    )

    _ingest_macro(object(), settings)

    assert not provider_calls, "macro provider must not be built when FRED_API_KEY is unset"


def test_ingest_macro_runs_with_key(monkeypatch) -> None:
    """With a key set, _ingest_macro feeds the configured series to ingest_macro_series."""
    settings = SimpleNamespace(fred_api_key="abc", macro_series_list=["CPIAUCSL", "UNRATE"])
    sentinel_provider = object()
    sentinel_session = object()

    monkeypatch.setattr(
        "markettrace.providers.registry.get_macro_provider",
        lambda source="fred": sentinel_provider,
    )

    captured: dict[str, object] = {}

    def _fake_ingest(session, provider, series_ids, *, now):
        captured["session"] = session
        captured["provider"] = provider
        captured["series_ids"] = series_ids
        return {s: 1 for s in series_ids}

    monkeypatch.setattr(
        "markettrace.pipeline.macro_ingest.ingest_macro_series", _fake_ingest
    )

    _ingest_macro(sentinel_session, settings)

    assert captured["session"] is sentinel_session
    assert captured["provider"] is sentinel_provider
    assert captured["series_ids"] == ["CPIAUCSL", "UNRATE"]


# ---------------------------------------------------------------------------
# _ingest_corpus — caps, 8-K filter, idempotency, isolation (unit test, no network)
# ---------------------------------------------------------------------------


def _corpus_refs(n: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(source="sec_edgar", external_id=f"acc-{i}", market="US")
        for i in range(n)
    ]


@pytest.fixture
def corpus_env(monkeypatch):
    """Shrink the corpus to one issuer and stub out the network + extractor."""
    monkeypatch.setattr(
        ingest_mod,
        "_CORPUS_US_ISSUERS",
        [{"ticker": "AAPL", "name": "Apple Inc.", "industry": "Technology"}],
    )
    monkeypatch.setattr(ingest_mod, "_CORPUS_PER_ISSUER", 2)
    monkeypatch.setattr(
        "markettrace.nlp.event_extractor.EventExtractor", lambda *a, **kw: object()
    )
    monkeypatch.setattr(ingest_mod, "get_price_provider", lambda *a, **kw: object())

    captured: dict = {}

    class _Disclosure:
        def resolve_ciks(self, tickers):
            captured["resolved_tickers"] = list(tickers)
            return {"AAPL": "0000320193"}

        def list_for_issuer(self, issuer_id, since, *, primary_ticker=None, forms=None):
            captured["forms"] = forms
            captured["primary_ticker"] = primary_ticker
            captured["issuer_id"] = issuer_id
            return _corpus_refs(3)  # more than the per-issuer cap

    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: _Disclosure())
    return captured


def test_corpus_seeds_caps_and_filters_to_8k(
    monkeypatch, mem_session, corpus_env, fake_settings
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        ingest_mod,
        "run_slice",
        lambda *a, **kw: calls.append((kw["ticker"], kw["ref"].external_id)),
    )

    _ingest_corpus_us(mem_session, None, fake_settings)

    # Only the first _CORPUS_PER_ISSUER (2) of the 3 listed refs are ingested.
    assert calls == [("AAPL", "acc-0"), ("AAPL", "acc-1")]
    # The 8-K form filter and ticker were forwarded to the provider.
    assert corpus_env["forms"] == ingest_mod._CORPUS_FORMS
    assert corpus_env["primary_ticker"] == "AAPL"
    # The issuer's Instrument was seeded so run_slice can resolve it.
    assert mem_session.query(Instrument).filter_by(ticker="AAPL").count() == 1


def test_corpus_skips_already_ingested_documents(
    monkeypatch, mem_session, corpus_env, fake_settings
) -> None:
    mem_session.add(
        Document(
            source="sec_edgar",
            external_id="acc-0",
            url="https://example.com",
            title="seed",
            content_hash="seedhash",
            market="US",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    mem_session.commit()

    sliced: list[str] = []
    monkeypatch.setattr(
        ingest_mod, "run_slice", lambda *a, **kw: sliced.append(kw["ref"].external_id)
    )
    recomputed: list[str] = []
    monkeypatch.setattr(
        ingest_mod,
        "recompute_document_outcomes",
        lambda *a, **kw: recomputed.append(kw["document"].external_id) or 1,
    )

    _ingest_corpus_us(mem_session, None, fake_settings)

    # acc-0 already exists -> no re-extraction, but stale/null outcomes are refreshed.
    assert sliced == ["acc-1"]
    assert recomputed == ["acc-0"]


def test_corpus_one_filing_failure_does_not_abort_issuer(
    monkeypatch, mem_session, corpus_env, fake_settings
) -> None:
    sliced: list[str] = []

    def _slice(*a, **kw):
        if kw["ref"].external_id == "acc-0":
            raise RuntimeError("boom: simulated slice failure")
        sliced.append(kw["ref"].external_id)

    monkeypatch.setattr(ingest_mod, "run_slice", _slice)

    _ingest_corpus_us(mem_session, None, fake_settings)

    # acc-0 failed but acc-1 was still ingested.
    assert sliced == ["acc-1"]


def test_requested_us_instrument_resolves_ticker_and_ingests_recent_filings(
    monkeypatch, mem_session, fake_settings
) -> None:
    captured: dict[str, object] = {}

    class _Disclosure:
        def resolve_issuer(self, query):
            captured["query"] = query
            return IssuerResolution("0001045810", "NVDA", "NVIDIA Corporation")

        def list_for_issuer(self, issuer_id, since, *, primary_ticker=None, forms=None):
            captured["issuer_id"] = issuer_id
            captured["primary_ticker"] = primary_ticker
            captured["forms"] = forms
            return _corpus_refs(3)

    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: _Disclosure())
    monkeypatch.setattr(ingest_mod, "get_price_provider", lambda *a, **kw: object())
    monkeypatch.setattr("markettrace.nlp.event_extractor.EventExtractor", lambda *a, **kw: object())

    sliced: list[str] = []
    monkeypatch.setattr(
        ingest_mod, "run_slice", lambda *a, **kw: sliced.append(kw["ref"].external_id)
    )

    request = InstrumentAnalyzeRequest(
        market="US",
        ticker="nvda",
        name="NVIDIA Corporation",
        industry="Technology",
        max_filings=2,
    )
    ingested = _ingest_requested_instrument(mem_session, None, fake_settings, request)

    assert ingested == 2
    assert captured["query"] == "NVDA"
    assert captured["issuer_id"] == "0001045810"
    assert captured["primary_ticker"] == "NVDA"
    assert captured["forms"] == ingest_mod._CORPUS_FORMS
    assert sliced == ["acc-0", "acc-1"]
    inst = mem_session.query(Instrument).filter_by(ticker="NVDA").one()
    assert inst.name == "NVIDIA Corporation"


def test_requested_instrument_missing_issuer_id_is_noop(
    monkeypatch, mem_session, fake_settings
) -> None:
    class _Disclosure:
        def resolve_issuer(self, query):
            return None

    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: _Disclosure())
    monkeypatch.setattr(ingest_mod, "get_price_provider", lambda *a, **kw: object())

    sliced: list[bool] = []
    monkeypatch.setattr(ingest_mod, "run_slice", lambda *a, **kw: sliced.append(True))

    request = InstrumentAnalyzeRequest(market="US", ticker="NOPE", max_filings=2)
    ingested = _ingest_requested_instrument(mem_session, None, fake_settings, request)

    assert ingested == 0
    assert not sliced


# ---------------------------------------------------------------------------
# _ingest_corpus_kr — corp_code resolution + forms-less provider fallback
# ---------------------------------------------------------------------------


def test_corpus_kr_resolves_corp_codes_and_handles_no_forms_kwarg(
    monkeypatch, mem_session, fake_settings
) -> None:
    monkeypatch.setattr(
        ingest_mod,
        "_CORPUS_KR_ISSUERS",
        [{"ticker": "005930", "name": "Samsung Electronics", "industry": "Technology"}],
    )
    monkeypatch.setattr(ingest_mod, "_CORPUS_PER_ISSUER", 2)
    monkeypatch.setattr("markettrace.nlp.event_extractor.EventExtractor", lambda *a, **kw: object())
    monkeypatch.setattr(ingest_mod, "get_price_provider", lambda *a, **kw: object())

    captured: dict = {}

    class _KrDisclosure:
        def resolve_corp_codes(self, tickers):
            captured["tickers"] = list(tickers)
            return {"005930": "00126380"}

        # No ``forms`` kwarg — _ingest_issuer_filings must fall back gracefully.
        def list_for_issuer(self, issuer_id, since, *, primary_ticker=None):
            captured["issuer_id"] = issuer_id
            captured["primary_ticker"] = primary_ticker
            return [
                SimpleNamespace(source="opendart", external_id=f"rcept-{i}", market="KR")
                for i in range(3)
            ]

    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: _KrDisclosure())

    sliced: list[str] = []
    monkeypatch.setattr(
        ingest_mod, "run_slice", lambda *a, **kw: sliced.append(kw["ref"].external_id)
    )

    _ingest_corpus_kr(mem_session, None, fake_settings)

    # corp_code resolved from the 6-digit ticker; capped at _CORPUS_PER_ISSUER (2).
    assert captured["issuer_id"] == "00126380"
    assert captured["primary_ticker"] == "005930"
    assert sliced == ["rcept-0", "rcept-1"]
    assert mem_session.query(Instrument).filter_by(ticker="005930").count() == 1


def test_corpus_kr_skipped_without_opendart_key(monkeypatch, mem_session) -> None:
    settings = SimpleNamespace(opendart_api_key=None)
    built: list[bool] = []
    monkeypatch.setattr(ingest_mod, "get_disclosure_provider", lambda *a, **kw: built.append(True))

    _ingest_corpus_kr(mem_session, None, settings)

    assert not built, "KR corpus must not build a provider when OPENDART_API_KEY is unset"


# ---------------------------------------------------------------------------
# _ingest_summary + CLI main (--summary-only) — corpus counts, no network
# ---------------------------------------------------------------------------


def _seed_event(session, *, ticker: str, n: int) -> None:
    inst = Instrument(market="US", ticker=ticker, name=ticker)
    session.add(inst)
    session.flush()
    for i in range(n):
        doc = Document(
            source="sec_edgar",
            external_id=f"{ticker}-{i}",
            url="https://example.com",
            title="seed",
            content_hash=f"{ticker}hash{i}",
            market="US",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(doc)
        session.flush()
        session.add(
            Event(
                document_id=doc.id,
                primary_instrument_id=inst.id,
                event_type="earnings",
                direction="positive",
                horizon_days=20,
                confidence=0.7,
                model="test",
                model_version="v1",
                analyzed_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
    session.commit()


def test_ingest_summary_counts_events_by_ticker(mem_session) -> None:
    _seed_event(mem_session, ticker="AAPL", n=3)
    _seed_event(mem_session, ticker="MSFT", n=1)

    summary = _ingest_summary(mem_session)

    assert summary["documents"] == 4
    assert summary["events"] == 4
    # Ordered by descending event count.
    assert list(summary["events_by_ticker"].items()) == [("AAPL", 3), ("MSFT", 1)]


def test_main_summary_only_skips_ingest(monkeypatch, mem_session, fake_settings) -> None:
    """main(--summary-only) prints counts without running the ingest worker."""
    _seed_event(mem_session, ticker="AAPL", n=2)

    ran: list[bool] = []
    monkeypatch.setattr(ingest_mod, "run_demo_ingest", lambda: ran.append(True))
    monkeypatch.setattr(
        ingest_mod, "get_settings", lambda: SimpleNamespace(database_url="sqlite://")
    )
    monkeypatch.setattr(ingest_mod, "make_engine", lambda url: object())
    monkeypatch.setattr(ingest_mod, "make_session_factory", lambda engine: lambda: mem_session)

    rc = main(["--summary-only"])

    assert rc == 0
    assert not ran, "--summary-only must not invoke run_demo_ingest"
