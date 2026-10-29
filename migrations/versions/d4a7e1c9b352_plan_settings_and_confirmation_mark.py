"""Transfer time in plan_settings; confirmation becomes a mark, not a status

The transfer time moves from the PLAN_TRANSFER_CUTOFF_HOUR env variable into a single-row
`plan_settings` table edited in the admin, seeded with the old default 10:00. Confirmation no
longer has a status of its own: `confirmed` positions go back to `draft` and keep their
`rs_confirmed` mark, which every confirmed position already carries.

Revision ID: d4a7e1c9b352
Revises: c3f8a6d2e417
Create Date: 2026-10-28
"""

import uuid
from datetime import time

import sqlalchemy as sa
from alembic import op

revision = "d4a7e1c9b352"
down_revision = "c3f8a6d2e417"
branch_labels = None
depends_on = None


def upgrade() -> None:
    settings = op.create_table(
        "plan_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transfer_time", sa.Time(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(settings, [{"id": uuid.uuid4(), "transfer_time": time(10, 0)}])
    op.execute("UPDATE plan_items SET status = 'draft', rs_confirmed = true WHERE status = 'confirmed'")


def downgrade() -> None:
    op.execute("UPDATE plan_items SET status = 'confirmed' WHERE status = 'draft' AND rs_confirmed")
    op.drop_table("plan_settings")
