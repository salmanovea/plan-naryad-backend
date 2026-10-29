"""Drop reconciliation_results.fact_is_late

The flag compared the fact's `submitted_at` with 20:00 of the plan day, but the mirror
never learns when a fact was entered in Raport — `submitted_at` is the moment the sync
copied it. Lateness cannot be tracked, so the flag is gone.

Revision ID: c3f8a6d2e417
Revises: b8e4d92a51c7
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "c3f8a6d2e417"
down_revision = "b8e4d92a51c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("reconciliation_results", "fact_is_late")


def downgrade() -> None:
    op.add_column(
        "reconciliation_results",
        sa.Column("fact_is_late", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
