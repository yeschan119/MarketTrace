"""Shared pytest fixtures.

These fixtures run entirely on in-memory SQLite — no postgres, network, or API
key required — and are intended to be reused by other modules' test suites.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from markettrace.db.models import Base
from markettrace.db.session import make_engine, make_session_factory
from markettrace.storage import ObjectStore


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A fresh in-memory SQLite engine with all tables created."""

    eng = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A function-scoped session that is rolled back and closed on teardown."""

    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def clear_issuer_registry_caches() -> Iterator[None]:
    """Drop the providers' cached SEC/DART issuer registries around each test.

    Both providers cache the parsed registry process-wide (the search box would
    otherwise re-download it per keystroke). Tests build providers with their own
    mock transports, so a cache surviving between them would serve one test's
    fixture rows to another.
    """
    from markettrace.providers.opendart import reset_corp_row_cache
    from markettrace.providers.sec_edgar import reset_company_row_cache

    reset_company_row_cache()
    reset_corp_row_cache()
    yield
    reset_company_row_cache()
    reset_corp_row_cache()


@pytest.fixture(autouse=True)
def offline_issuer_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ``/instruments/search`` offline unless a test opts in.

    The endpoint falls back to the live SEC/DART registries for issuers the
    corpus has not collected yet. Tests that exercise that fallback re-patch
    ``_registry_matches`` themselves; every other test must stay network-free.
    """
    from markettrace.api import routes

    monkeypatch.setattr(routes, "_registry_matches", lambda query, limit: [])


@pytest.fixture
def tmp_object_store(tmp_path: Path) -> ObjectStore:
    """An ``ObjectStore`` rooted in a temporary directory."""

    return ObjectStore(tmp_path / "objectstore")
