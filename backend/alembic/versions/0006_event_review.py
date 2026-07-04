"""event human-review columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-04

Adds Phase 2 human-review provenance to ``events``: a ``reviewed_at`` timestamp
and ``original_*`` snapshots capturing the model's values before the first
manual correction, so the LLM read stays recoverable and auditable.

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "events", sa.Column("original_direction", sa.String(), nullable=True)
    )
    op.add_column(
        "events", sa.Column("original_event_type", sa.String(), nullable=True)
    )
    op.add_column(
        "events", sa.Column("original_confidence", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("events", "original_confidence")
    op.drop_column("events", "original_event_type")
    op.drop_column("events", "original_direction")
    op.drop_column("events", "reviewed_at")
