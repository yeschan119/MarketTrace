"""Pure Student-t p-value primitives (no SciPy, no ORM).

Extracted so both the significance report (:mod:`markettrace.impact.significance`)
and the significance-gated signal model (:mod:`markettrace.impact.signal`) can
share one implementation of the two-sided t p-value without either pulling in the
other's dependency chain (the ORM/statistics stack on one side, the deliberately
dependency-free signal models on the other).

The p-value is computed from the regularised incomplete beta function
(Numerical Recipes ``betai``/``betacf``), which needs only the standard library.
"""

from __future__ import annotations

from math import exp, lgamma, log

__all__ = ["two_sided_t_pvalue"]


def _betacf(a: float, b: float, x: float) -> float:
    """Continued-fraction expansion for the incomplete beta function."""
    maxit = 200
    eps = 3.0e-12
    fpmin = 1.0e-300

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = lgamma(a + b) - lgamma(a) - lgamma(b)
    bt = exp(ln_beta + a * log(x) + b * log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def two_sided_t_pvalue(t_stat: float, df: int) -> float | None:
    """Two-sided p-value for a Student-t statistic with ``df`` degrees of freedom.

    Uses the identity ``p = I_{df/(df+t^2)}(df/2, 1/2)``. Returns ``None`` when
    ``df <= 0`` (fewer than two observations).
    """
    if df <= 0:
        return None
    x = df / (df + t_stat * t_stat)
    return _betai(df / 2.0, 0.5, x)
