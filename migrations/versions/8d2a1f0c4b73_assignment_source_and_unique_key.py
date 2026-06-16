"""contractor_assignments: add source + composite unique key

Revision ID: 8d2a1f0c4b73
Revises: 37491b6c8181
Create Date: 2026-06-15 13:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8d2a1f0c4b73"
down_revision: Union[str, None] = "37491b6c8181"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contractor_assignments",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.create_index(
        "uq_contractor_assignments_key",
        "contractor_assignments",
        ["contractor_id", "housing_id", "section_id", "work_group_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index("uq_contractor_assignments_key", table_name="contractor_assignments")
    op.drop_column("contractor_assignments", "source")
