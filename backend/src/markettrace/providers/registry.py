"""Provider registry.

Maps market strings to concrete provider implementations.
"""

from __future__ import annotations

from markettrace.providers.base import DisclosureProvider, PriceProvider

__all__ = ["get_disclosure_provider", "get_price_provider"]


def get_disclosure_provider(market: str, **kw) -> DisclosureProvider:
    """Return a ``DisclosureProvider`` for the given market.

    Parameters
    ----------
    market:
        Market identifier, e.g. ``"US"``.
    **kw:
        Forwarded to the provider constructor.  For ``"US"`` this must include
        ``user_agent: str`` and may include ``client``, ``watchlist``.

    Raises
    ------
    ValueError
        When ``market`` is not supported.
    """
    if market == "US":
        from markettrace.providers.sec_edgar import SecEdgarProvider

        return SecEdgarProvider(**kw)  # type: ignore[return-value]

    raise ValueError(f"Unknown disclosure market: {market!r}")


def get_price_provider(market: str, **kw) -> PriceProvider:
    """Return a ``PriceProvider`` for the given market.

    Parameters
    ----------
    market:
        Market identifier, e.g. ``"US"``.
    **kw:
        Forwarded to the provider constructor.  For ``"US"`` this may include
        ``client``.

    Raises
    ------
    ValueError
        When ``market`` is not supported.
    """
    if market == "US":
        from markettrace.providers.stooq import StooqPriceProvider

        return StooqPriceProvider(**kw)  # type: ignore[return-value]

    raise ValueError(f"Unknown price market: {market!r}")
