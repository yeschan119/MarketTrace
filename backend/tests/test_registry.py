"""Tests for the price-provider registry selection."""

from __future__ import annotations

import pytest

from markettrace.config import get_settings
from markettrace.providers.registry import get_price_provider
from markettrace.providers.stooq import StooqPriceProvider
from markettrace.providers.tiingo import TiingoPriceProvider


class TestGetPriceProvider:
    def test_explicit_tiingo(self):
        assert isinstance(get_price_provider("US", provider="tiingo"), TiingoPriceProvider)

    def test_explicit_stooq(self):
        assert isinstance(get_price_provider("US", provider="stooq"), StooqPriceProvider)

    def test_default_follows_settings(self):
        name = get_settings().price_provider
        expected = TiingoPriceProvider if name == "tiingo" else StooqPriceProvider
        assert isinstance(get_price_provider("US"), expected)

    def test_unknown_market_raises(self):
        with pytest.raises(ValueError, match="Unknown price market"):
            get_price_provider("KR")

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown price provider"):
            get_price_provider("US", provider="bogus")
