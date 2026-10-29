"""Per-contractor position limits replace per-(contractor, work) floor limits

The ТЗ limit caps one contractor's positions in a day plan whatever the mix of
works, so the work column lost its meaning. The old table is empty everywhere
(no UI existed to fill it), so this is a drop-and-create, not a data migration.

Revision ID: b8e4d92a51c7
Revises: a7d3c1f42b90
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op

revision = "b8e4d92a51c7"
down_revision = "a7d3c1f42b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("contractor_floor_limits")
    op.create_table(
        "contractor_position_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contractor_id", sa.Uuid(), nullable=False),
        sa.Column("positions_limit", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["contractors.id"], name="fk_contractor_position_limits_contractor_id"
        ),
    )
    op.create_index(
        "uq_contractor_position_limits_contractor", "contractor_position_limits", ["contractor_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("contractor_position_limits")
    op.create_table(
        "contractor_floor_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contractor_id", sa.Uuid(), nullable=True),
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column("floors_limit", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"], name="fk_contractor_floor_limits_contractor_id"),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], name="fk_contractor_floor_limits_work_id"),
    )
    op.create_index(
        "uq_contractor_floor_limits_key",
        "contractor_floor_limits",
        ["contractor_id", "work_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
