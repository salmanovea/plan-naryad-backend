"""tech_sequence_items: section scope and explicit FS/SS predecessors.

Two facts about Raport calendar plans that the previous shape could not hold:

  * plans are built per housing **and** per housing+section (11 of 19 plans in the dev
    database are section-scoped), so a section needs its own sequence rows;
  * predecessor links carry a type, and the data mixes them — 132 042 finish-to-start
    edges against 11 016 start-to-start. One `dependency_type` column per node cannot
    describe a node whose predecessors differ, so it is replaced by two arrays.

Existing rows all came from the housing-wide plan with `dependency_type =
finish_to_start`, so they keep `section_id = NULL` and an empty `depends_on_ss`.

Revision ID: c3a80d4517be
Revises: b7f1c02e9a34
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a80d4517be"
down_revision: Union[str, None] = "b7f1c02e9a34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tech_sequence_items", sa.Column("section_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_tech_sequence_items_section_id",
        "tech_sequence_items",
        "sections",
        ["section_id"],
        ["id"],
    )
    op.create_index("ix_tech_sequence_items_section_id", "tech_sequence_items", ["section_id"])

    op.add_column(
        "tech_sequence_items",
        sa.Column("depends_on_ss", sa.ARRAY(sa.String()), nullable=True, server_default="{}"),
    )
    op.execute("UPDATE tech_sequence_items SET depends_on_ss = '{}' WHERE depends_on_ss IS NULL")
    op.alter_column("tech_sequence_items", "depends_on_ss", nullable=False)

    # Every existing row is finish-to-start, so nothing moves into depends_on_ss.
    op.drop_column("tech_sequence_items", "dependency_type")

    # The key now includes the scope: a section-scoped row coexists with the housing-wide
    # one for the same work. NULLS NOT DISTINCT keeps housing-wide rows unique.
    op.drop_index("uq_tech_sequence_items_key", table_name="tech_sequence_items")
    op.execute(
        "CREATE UNIQUE INDEX uq_tech_sequence_items_key "
        "ON tech_sequence_items (housing_id, section_id, work_id) NULLS NOT DISTINCT"
    )


def downgrade() -> None:
    op.drop_index("uq_tech_sequence_items_key", table_name="tech_sequence_items")

    # Section-scoped rows have no place in the old shape and would break the narrower key.
    op.execute("DELETE FROM tech_sequence_items WHERE section_id IS NOT NULL")

    op.add_column(
        "tech_sequence_items",
        sa.Column("dependency_type", sa.String(length=20), nullable=True, server_default="finish_to_start"),
    )
    op.execute("UPDATE tech_sequence_items SET dependency_type = 'finish_to_start'")
    op.execute(
        "UPDATE tech_sequence_items SET dependency_type = 'start_to_start' "
        "WHERE depends_on_ss IS NOT NULL AND array_length(depends_on_ss, 1) > 0"
    )

    op.drop_column("tech_sequence_items", "depends_on_ss")
    op.drop_index("ix_tech_sequence_items_section_id", table_name="tech_sequence_items")
    op.drop_constraint("fk_tech_sequence_items_section_id", "tech_sequence_items", type_="foreignkey")
    op.drop_column("tech_sequence_items", "section_id")

    op.create_index(
        "uq_tech_sequence_items_key",
        "tech_sequence_items",
        ["housing_id", "work_id"],
        unique=True,
    )
