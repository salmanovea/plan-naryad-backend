"""work_facts: mirrored from Raport, so contractor and unit become optional.

Facts are entered in Raport only and pulled in from there. Two consequences measured on the
reference housing (56 365 facts):

  * `work_cell_contractor_id` and `contractor_id` come back empty on **every** fact, so the
    contractor is derived from the cell's assignment. That resolves 99.5% of cells; the rest
    carry more than one contractor and cannot be attributed — the fact is still stored with
    `contractor_id = NULL`, because dropping it would lose «факт без плана» rows in
    reconciliation.
  * `unit` is not always present in the Raport payload.

`raport_id` is added as the upsert key (Raport's `work_fact.id`). `reconciliation_results`
follows suit: a fact nobody can attribute still has to appear as an unplanned row.

Revision ID: d5b2914e07af
Revises: c3a80d4517be
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5b2914e07af"
down_revision: Union[str, None] = "c3a80d4517be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("work_facts", "contractor_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("work_facts", "unit", existing_type=sa.String(length=20), nullable=True)

    op.add_column("work_facts", sa.Column("raport_id", sa.String(length=255), nullable=True))
    op.create_index("ix_work_facts_raport_id", "work_facts", ["raport_id"], unique=True)

    # A fact without an attributable contractor still has to produce a reconciliation row —
    # that is exactly the «фактически выполненные работы, которых не было в план-наряде» case.
    op.alter_column("reconciliation_results", "contractor_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM reconciliation_results WHERE contractor_id IS NULL")
    op.alter_column("reconciliation_results", "contractor_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_index("ix_work_facts_raport_id", table_name="work_facts")
    op.drop_column("work_facts", "raport_id")

    # Rows without a contractor cannot exist in the old shape.
    op.execute("DELETE FROM work_facts WHERE contractor_id IS NULL")
    op.execute("UPDATE work_facts SET unit = '' WHERE unit IS NULL")
    op.alter_column("work_facts", "unit", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("work_facts", "contractor_id", existing_type=sa.Uuid(), nullable=False)
