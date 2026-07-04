"""Canonical event-type taxonomy — the single source of truth for event families.

The extractor's ``event_type`` is constrained to one of a small set of canonical
families (:data:`CANONICAL_FAMILIES`) so the live corpus does not fragment into
100+ near-synonym labels (``earnings_release`` / ``earnings_beat`` /
``earnings_guide``, ``insider_trading_report`` / ``insider_sale`` /
``internal_transaction``, and so on). Fragmentation splits each family's sample
across many strings and dilutes the signal statistics that group by
``event_type``.

Enforcement happens in two places, both driven by this module:

* :mod:`markettrace.nlp.schemas` injects :data:`CANONICAL_FAMILIES` as the
  ``enum`` on the extraction tool schema (constraining the LLM) and canonicalizes
  the returned value defensively.
* :mod:`markettrace.eval.taxonomy` re-exports these symbols so the eval harness
  scores at the family level.

:func:`canonicalize` collapses a raw event type into a family using
deterministic, ordered substring rules. The rule order matters: more specific
families are tested first so that, e.g., ``treasury_stock_acquisition`` maps to
``buyback`` before the generic ``stock_acquisition`` -> ``merger_acquisition``
rule can claim it, and ``earnings_conference_call`` maps to ``earnings`` before
the ``conference`` -> ``ir_event`` rule.

This module is a pure leaf (no imports) so both ``nlp`` and ``eval`` can depend
on it without any layering cycle.
"""

from __future__ import annotations

__all__ = ["CANONICAL_FAMILIES", "OTHER", "canonicalize", "canonical_rules"]

OTHER = "other"

# Ordered (canonical_family, trigger_substrings) rules. First family with any
# trigger appearing in the lower-cased raw event type wins.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("insider_trading", ("insider", "internal_transaction", "trading_plan")),
    ("buyback", ("buyback", "treasury_stock")),
    ("dividend", ("dividend",)),
    ("guidance", ("guidance", "earnings_guide")),
    ("earnings", ("earnings", "sales_report")),
    (
        "merger_acquisition",
        ("merger", "asset_disposal", "asset_transfer", "real_estate", "stock_acquisition"),
    ),
    (
        "capital_raise",
        (
            "debt_offering",
            "debt_issuance",
            "bond_issuance",
            "capital_increase",
            "capital_raising",
            "equity_offering",
            "preferred_stock",
            "registration_statement",
            "exchange_offer",
            "redemption",
            "conversion_rate",
            "credit_agreement",
            "loan",
            "financing",
        ),
    ),
    ("ownership_change", ("ownership", "shareholding", "holding_change")),
    (
        "shareholder_meeting",
        (
            "shareholder_meeting",
            "annual_meeting",
            "general_meeting",
            "shareholder_vote",
            "shareholder_approval",
            "proxy",
            "bylaw",
        ),
    ),
    (
        "governance",
        (
            "board",
            "director",
            "executive",
            "management",
            "leadership",
            "appointment",
            "resignation",
            "retirement",
            "departure",
            "dismissal",
            "compensation",
            "equity_award",
            "stock_plan",
            "employment_agreement",
        ),
    ),
    # Note: regulation_fd_disclosure is deliberately NOT here — Reg FD is a
    # disclosure *vehicle* for arbitrary content, not a regulatory action, so it
    # falls through to OTHER rather than inflating the enforcement family.
    ("regulatory", ("regulatory", "lawsuit", "litigation", "infringement", "settlement")),
    ("esg_report", ("sustainability", "esg_report", "report_release", "donation")),
    ("ir_event", ("investor", "conference")),
    ("contract_partnership", ("contract", "partnership")),
    ("investment", ("investment",)),
    ("product", ("product",)),
    ("macro", ("macro",)),
)

# The canonical family set, including the OTHER fallback.
CANONICAL_FAMILIES: frozenset[str] = frozenset({fam for fam, _ in _RULES} | {OTHER})


def canonical_rules() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the ordered (family, triggers) rule table (for tests/inspection)."""
    return _RULES


def canonicalize(event_type: str) -> str:
    """Map a raw event type to its canonical family.

    Matching is case-insensitive substring on the ordered rule table; the first
    family with a matching trigger wins. Unmatched types (genuinely vague
    labels like ``corporate_disclosure`` or ``company_update``) fall back to
    :data:`OTHER`. Idempotent on canonical families: a family name maps to itself.
    """
    key = event_type.strip().lower()
    if key in CANONICAL_FAMILIES:
        return key
    for family, triggers in _RULES:
        if any(trigger in key for trigger in triggers):
            return family
    return OTHER
