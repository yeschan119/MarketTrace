"""Market-adjusted abnormal return model.

This module implements the *market-adjusted* model, which assumes beta = 1 for
all instruments within the estimation window of the vertical slice.  The
abnormal return (AR) is therefore simply the stock's return minus the market
(index) return over the same interval:

    AR = R_stock - R_market

A full market-model regression (estimating alpha and beta from a pre-event
window) is a Phase-4 extension once sufficient price history is available.
"""

from __future__ import annotations


def abnormal_return(stock_return: float, market_return: float) -> float:
    """Return the market-adjusted abnormal return.

    Parameters
    ----------
    stock_return:
        Cumulative log or simple return of the stock over the horizon.
    market_return:
        Cumulative return of the benchmark index over the same horizon.

    Returns
    -------
    float
        ``stock_return - market_return``.  Positive values indicate
        outperformance relative to the market.
    """
    return stock_return - market_return


def sector_adjusted_return(stock_return: float, sector_return: float) -> float:
    """Return the industry/sector-adjusted abnormal return.

    Same beta = 1 assumption as :func:`abnormal_return`, but benchmarked
    against a sector index (e.g. a semiconductor ETF) instead of the broad
    market::

        AR_sector = R_stock - R_sector

    Subtracting the sector return strips out moves common to the whole
    industry, isolating the stock's idiosyncratic reaction to the event.
    A two-factor (market + sector) decomposition reduces to this pure
    sector-relative figure, so it is exposed as its own function.

    Parameters
    ----------
    stock_return:
        Cumulative simple return of the stock over the horizon.
    sector_return:
        Cumulative return of the sector benchmark over the same horizon.

    Returns
    -------
    float
        ``stock_return - sector_return``.
    """
    return stock_return - sector_return
