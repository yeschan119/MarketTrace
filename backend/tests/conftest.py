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


@pytest.fixture
def tmp_object_store(tmp_path: Path) -> ObjectStore:
    """An ``ObjectStore`` rooted in a temporary directory."""

    return ObjectStore(tmp_path / "objectstore")
