"""FastAPI dependencies for the MarketTrace read API."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from markettrace.config import get_settings
from markettrace.db.session import make_engine, make_session_factory


def get_db() -> Iterator[Session]:
    """Yield a SQLAlchemy Session built from settings.database_url.

    Override this dependency in tests via app.dependency_overrides[get_db].
    """
    engine = make_engine(get_settings().database_url)
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
