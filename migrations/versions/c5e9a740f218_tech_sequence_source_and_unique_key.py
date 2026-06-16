"""tech_sequence_items: add source + composite unique key

Revision ID: c5e9a740f218
Revises: 8d2a1f0c4b73
Create Date: 2026-06-15 14:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5e9a740f218"
down_revision: Union[str, None] = "8d2a1f0c4b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tech_sequence_items",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.create_index(
        "uq_tech_sequence_items_key",
        "tech_sequence_items",
        ["housing_id", "work_type_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_tech_sequence_items_key", table_name="tech_sequence_items")
    op.drop_column("tech_sequence_items", "source")
