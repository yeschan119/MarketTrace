"""phase 3: sector-adjusted outcome columns + event_impacts table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-14

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Sector/industry-adjusted figures alongside the existing market-adjusted ones.
    op.add_column("outcomes", sa.Column("sector_return", sa.Float(), nullable=True))
    op.add_column(
        "outcomes", sa.Column("sector_abnormal_return", sa.Float(), nullable=True)
    )

    op.create_table(
        "event_impacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column(
            "instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("industry", sa.String(), nullable=True),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("abnormal_return", sa.Float(), nullable=True),
        sa.Column("sector_abnormal_return", sa.Float(), nullable=True),
        sa.Column("signed_abnormal_return", sa.Float(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "event_id", "horizon_days", name="uq_event_impacts_event_horizon"
        ),
    )


def downgrade() -> None:
    op.drop_table("event_impacts")
    op.drop_column("outcomes", "sector_abnormal_return")
    op.drop_column("outcomes", "sector_return")
