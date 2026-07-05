"""event instrument-correction snapshot column

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-05

Adds ``events.original_primary_instrument_id`` so the model's original
company linkage is snapshotted on the first manual review, mirroring the
existing ``original_direction/event_type/confidence`` columns (0006). This
lets an admin correct a mis-linked instrument while keeping the LLM read
recoverable and auditable.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Batch mode keeps this portable: a pass-through ALTER on PostgreSQL (prod) and
# the copy-and-move strategy SQLite requires for adding a foreign-key constraint.
def upgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(
            sa.Column("original_primary_instrument_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_events_original_primary_instrument_id_instruments",
            "instruments",
            ["original_primary_instrument_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_constraint(
            "fk_events_original_primary_instrument_id_instruments",
            type_="foreignkey",
        )
        batch_op.drop_column("original_primary_instrument_id")
