"""Tests for impact.sector_index: industry -> sector-benchmark resolution."""

from __future__ import annotations

from markettrace.impact.sector_index import resolve_sector_index


def test_us_technology_maps_to_xlk() -> None:
    assert resolve_sector_index("US", "Technology") == "XLK"


def test_industry_match_is_case_insensitive() -> None:
    assert resolve_sector_index("US", "  technology ") == "XLK"
    assert resolve_sector_index("us", "ENERGY") == "XLE"


def test_kr_technology_maps_to_semiconductor_etf() -> None:
    assert resolve_sector_index("KR", "Technology") == "091160"


def test_unknown_industry_returns_none() -> None:
    assert resolve_sector_index("US", "Widgets") is None


def test_none_industry_returns_none() -> None:
    assert resolve_sector_index("US", None) is None


def test_unknown_market_returns_none() -> None:
    assert resolve_sector_index("JP", "Technology") is None
