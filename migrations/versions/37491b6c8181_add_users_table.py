"""add users table

Revision ID: 37491b6c8181
Revises: fca870ab8a4b
Create Date: 2026-06-15 13:21:06.093183

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "37491b6c8181"
down_revision: Union[str, None] = "fca870ab8a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("middle_name", sa.String(length=255), nullable=True),
        sa.Column("shown_name", sa.String(length=500), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("is_external", sa.Boolean(), nullable=False),
        sa.Column("groups", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("project_ids", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("contractor_ids", sa.ARRAY(sa.String()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("raport_id", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_raport_id"), "users", ["raport_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_raport_id"), table_name="users")
    op.drop_table("users")
