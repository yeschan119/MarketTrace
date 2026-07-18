"""ledger / passbook category customization

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_category_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("keyword_norm", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("domain", "keyword_norm", name="uq_ledger_rule_domain_keyword"),
    )
    op.create_table(
        "ledger_entry_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("entry_key", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("domain", "entry_key", name="uq_ledger_override_domain_key"),
    )
    op.create_table(
        "ledger_custom_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("domain", "name", name="uq_ledger_custom_category"),
    )


def downgrade() -> None:
    op.drop_table("ledger_custom_categories")
    op.drop_table("ledger_entry_overrides")
    op.drop_table("ledger_category_rules")
