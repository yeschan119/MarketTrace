"""canonicalize stored event_type into the fixed family taxonomy

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-04

Collapses the free-text ``events.event_type`` (and the ``event_impacts``
snapshot copy) into the ~18 canonical families now enforced at extraction time
(see ``markettrace.nlp.taxonomy``). Existing rows were written before the enum
was in place, so the corpus fragmented into 100+ near-synonym labels; grouping
them by family here restores the sample size the signal statistics depend on.

The rule table is embedded verbatim (not imported from app code) so this
migration stays reproducible even if the taxonomy later evolves — an Alembic
migration is an immutable snapshot. ``downgrade`` is a no-op: the collapse is
lossy (the original raw sub-label is not recoverable) and the family is the
meaningful unit.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OTHER = "other"

# Frozen snapshot of markettrace.nlp.taxonomy._RULES as of 2026-07-04. Ordered:
# the first family with any trigger appearing in the lower-cased raw type wins.
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
    ("regulatory", ("regulatory", "lawsuit", "litigation", "infringement", "settlement")),
    ("esg_report", ("sustainability", "esg_report", "report_release", "donation")),
    ("ir_event", ("investor", "conference")),
    ("contract_partnership", ("contract", "partnership")),
    ("investment", ("investment",)),
    ("product", ("product",)),
    ("macro", ("macro",)),
)

_FAMILIES: frozenset[str] = frozenset({fam for fam, _ in _RULES} | {_OTHER})


def _canonicalize(event_type: str) -> str:
    key = (event_type or "").strip().lower()
    if key in _FAMILIES:
        return key
    for family, triggers in _RULES:
        if any(trigger in key for trigger in triggers):
            return family
    return _OTHER


def _rewrite(table: str) -> None:
    """Map every distinct raw event_type in *table* to its canonical family."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(f"SELECT DISTINCT event_type FROM {table}")  # noqa: S608 - table is a literal
    ).fetchall()
    for (raw,) in rows:
        if raw is None:
            continue
        family = _canonicalize(raw)
        if family == raw:
            continue
        conn.execute(
            sa.text(
                f"UPDATE {table} SET event_type = :fam "  # noqa: S608 - table is a literal
                "WHERE event_type = :raw"
            ),
            {"fam": family, "raw": raw},
        )


def upgrade() -> None:
    _rewrite("events")
    _rewrite("event_impacts")


def downgrade() -> None:
    # Lossy collapse — the original raw sub-label is not recoverable. No-op.
    pass
