"""phase 3: macro_observations table (FRED/ALFRED vintage releases + surprise)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "macro_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("released_value", sa.Float(), nullable=False),
        sa.Column("previous_value", sa.Float(), nullable=True),
        sa.Column("expected_value", sa.Float(), nullable=True),
        sa.Column("expected_source", sa.String(), nullable=True),
        sa.Column("surprise_score", sa.Float(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(), nullable=False),
        sa.UniqueConstraint(
            "series_id", "reference_date", "revision", name="uq_macro_obs_series_ref_rev"
        ),
    )


def downgrade() -> None:
    op.drop_table("macro_observations")
