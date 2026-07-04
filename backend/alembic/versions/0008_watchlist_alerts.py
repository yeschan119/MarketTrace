"""watchlist + in-app alerts

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-04

Adds the Phase 5 watchlist-alert feature: ``watchlist_items`` (instruments the
admin watches) and ``alerts`` (in-app notifications generated during ingest when
a watched instrument gets a notable new event — a validated-significant type,
flagged ``conflict`` when the model direction opposes the historical drift).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("instrument_id", name="uq_watchlist_instrument"),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id"),
            nullable=False,
        ),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_alerts_event"),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("watchlist_items")
