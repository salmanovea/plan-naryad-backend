"""add contracts table

Revision ID: fca870ab8a4b
Revises: 6ae947202dd1
Create Date: 2026-06-15 13:12:15.621394

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fca870ab8a4b"
down_revision: Union[str, None] = "6ae947202dd1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("contractor_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("is_warranty_letter", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("raport_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"], name="fk_contracts_contractor_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contracts_contractor_id"), "contracts", ["contractor_id"], unique=False)
    op.create_index(op.f("ix_contracts_raport_id"), "contracts", ["raport_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_contracts_raport_id"), table_name="contracts")
    op.drop_index(op.f("ix_contracts_contractor_id"), table_name="contracts")
    op.drop_table("contracts")
