"""Drop plan_adjustments — editing a position is now delete + re-add.

The spec replaced in-place edits: «Редактирование автоматически сформированной позиции
выполняется через её удаление и добавление новой позиции с корректными параметрами». With
`POST /plan-naryad/{id}/adjust` gone there is nothing left to journal here; the four actions
the spec does want traced live in `action_logs`.

Revision ID: e91c47a3d268
Revises: d5b2914e07af
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e91c47a3d268"
down_revision: Union[str, None] = "d5b2914e07af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("plan_adjustments")


def downgrade() -> None:
    op.create_table(
        "plan_adjustments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("plan_item_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("original_field", sa.String(length=50), nullable=False),
        sa.Column("original_value", sa.String(length=255), nullable=False),
        sa.Column("new_value", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("adjusted_by", sa.String(length=255), nullable=False),
        sa.Column("adjusted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_item_id"], ["plan_items.id"], name="fk_plan_adjustments_plan_item_id"),
    )
    op.create_index("ix_plan_adjustments_plan_item_id", "plan_adjustments", ["plan_item_id"])
