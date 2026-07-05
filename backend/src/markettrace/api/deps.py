"""FastAPI dependencies for the MarketTrace read API."""

from __future__ import annotations

from collections.abc import Callable, Iterator

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


def get_price_provider_factory() -> Callable[[str], object]:
    """Return a ``market -> PriceProvider`` factory.

    The instrument-correction path (PATCH /events/{id}) re-fetches prices to
    recompute outcomes for the newly linked company. Isolating the factory as a
    dependency lets tests inject a fake provider (no network) via
    ``app.dependency_overrides[get_price_provider_factory]``.
    """
    from markettrace.providers.registry import get_price_provider

    def factory(market: str) -> object:
        return get_price_provider(market)

    return factory
