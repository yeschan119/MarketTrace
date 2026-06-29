"""passbook statements monthly storage

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-29

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "passbook_statements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("statement_month", sa.Date(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encrypted", sa.Boolean(), nullable=False),
        sa.Column("account_no", sa.String(), nullable=True),
        sa.Column("account_holder", sa.String(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("closing_balance", sa.Integer(), nullable=True),
        sa.Column("withdrawal_total", sa.Integer(), nullable=False),
        sa.Column("deposit_total", sa.Integer(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.UniqueConstraint("statement_month", name="uq_passbook_statements_month"),
    )


def downgrade() -> None:
    op.drop_table("passbook_statements")
