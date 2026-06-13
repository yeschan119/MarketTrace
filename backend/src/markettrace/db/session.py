"""SQLAlchemy 2.0 engine and session factories.

Factory functions accept an explicit URL so they stay testable (tests pass an
in-memory SQLite URL). Module-level ``get_engine`` / ``SessionLocal`` are built
lazily from settings for application use, with override support.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from markettrace.config import get_settings
from markettrace.db.models import Base

__all__ = [
    "Base",
    "make_engine",
    "make_session_factory",
    "get_engine",
    "get_session_factory",
    "SessionLocal",
]


def make_engine(url: str, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine for the given database URL."""

    return create_engine(url, echo=echo, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine."""

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(url: str | None = None) -> Engine:
    """Return a process-wide engine, building it from settings on first use.

    Passing ``url`` rebuilds the engine against that URL (useful for overrides).
    """

    global _engine, _session_factory
    if url is not None or _engine is None:
        resolved = url or get_settings().database_url
        _engine = make_engine(resolved)
        _session_factory = make_session_factory(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory, building it on first use."""

    global _session_factory
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


def SessionLocal() -> Session:
    """Open a new ``Session`` from the process-wide factory."""

    return get_session_factory()()
