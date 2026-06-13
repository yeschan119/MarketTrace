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

    if market == "KR":
        from markettrace.config import get_settings
        from markettrace.providers.opendart import OpenDartProvider

        kw.setdefault("api_key", get_settings().opendart_api_key)
        return OpenDartProvider(**kw)  # type: ignore[return-value]

    raise ValueError(f"Unknown disclosure market: {market!r}")


def get_price_provider(market: str, *, provider: str | None = None, **kw) -> PriceProvider:
    """Return a ``PriceProvider`` for the given market.

    Parameters
    ----------
    market:
        Market identifier, e.g. ``"US"``.
    provider:
        Override the configured implementation (``"tiingo"`` or ``"stooq"``).
        When ``None``, ``Settings.price_provider`` decides.
    **kw:
        Forwarded to the provider constructor (e.g. ``client``, ``api_key``).

    Raises
    ------
    ValueError
        When ``market`` or the resolved provider name is not supported.
    """
    if market == "US":
        from markettrace.config import get_settings

        settings = get_settings()
        name = provider or settings.price_provider

        if name == "tiingo":
            from markettrace.providers.tiingo import TiingoPriceProvider

            kw.setdefault("api_key", settings.tiingo_api_key)
            return TiingoPriceProvider(**kw)  # type: ignore[return-value]

        if name == "stooq":
            from markettrace.providers.stooq import StooqPriceProvider

            return StooqPriceProvider(**kw)  # type: ignore[return-value]

        raise ValueError(f"Unknown price provider: {name!r}")

    if market == "KR":
        from markettrace.providers.kr_naver import KrNaverPriceProvider

        return KrNaverPriceProvider(**kw)  # type: ignore[return-value]

    raise ValueError(f"Unknown price market: {market!r}")
