"""Map an instrument's industry to a sector-benchmark ticker.

The impact module computes a sector-adjusted abnormal return by subtracting a
sector index's return from the stock's. This module resolves *which* index to
use from the instrument's ``industry`` label, per market:

- US: the Select Sector SPDR ETFs (XLK, XLF, ...), available from the same
  price providers (Tiingo / stooq) used for stocks.
- KR: a representative sector ETF resolvable via the Naver price provider.

``resolve_sector_index`` returns ``None`` when the industry is unknown or has no
mapped benchmark (e.g. the market index itself), in which case the slice simply
skips the sector-adjusted figure.
"""

from __future__ import annotations

__all__ = ["SECTOR_INDEX_BY_MARKET", "resolve_sector_index"]

# market -> {industry (lowercased): benchmark ticker}
SECTOR_INDEX_BY_MARKET: dict[str, dict[str, str]] = {
    "US": {
        "technology": "XLK",
        "information technology": "XLK",
        "financials": "XLF",
        "financial": "XLF",
        "energy": "XLE",
        "health care": "XLV",
        "healthcare": "XLV",
        "industrials": "XLI",
        "consumer discretionary": "XLY",
        "consumer staples": "XLP",
        "utilities": "XLU",
        "materials": "XLB",
        "real estate": "XLRE",
        "communication services": "XLC",
    },
    "KR": {
        # KODEX 반도체 (semiconductor) — the closest liquid sector proxy for the
        # current KR universe (Samsung). Extend as the universe grows.
        "technology": "091160",
        "semiconductor": "091160",
    },
}


def resolve_sector_index(market: str, industry: str | None) -> str | None:
    """Return the sector-benchmark ticker for *industry* in *market*, or ``None``.

    Matching is case-insensitive on the industry label. Unknown markets or
    industries (and ``None`` industries) resolve to ``None``.
    """
    if industry is None:
        return None
    market_map = SECTOR_INDEX_BY_MARKET.get(market.upper())
    if market_map is None:
        return None
    return market_map.get(industry.strip().lower())
