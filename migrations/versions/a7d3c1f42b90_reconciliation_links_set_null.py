"""Reconciliation links survive their source rows: FK ondelete SET NULL

`reconciliation_results.plan_item_id` / `work_fact_id` are historical breadcrumbs,
not ownership. Without ON DELETE SET NULL, deleting a plan item from the UI (or a
work fact dropped by the sync snapshot diff) hits the FK and turns into a 500
(DEV-6858, item 18).

Revision ID: a7d3c1f42b90
Revises: e91c47a3d268
Create Date: 2026-09-01
"""

from alembic import op

revision = "a7d3c1f42b90"
down_revision = "e91c47a3d268"
branch_labels = None
depends_on = None

_TABLE = "reconciliation_results"
_FKS = [
    ("fk_reconciliation_results_plan_item_id", "plan_item_id", "plan_items"),
    ("fk_reconciliation_results_work_fact_id", "work_fact_id", "work_facts"),
]


def upgrade() -> None:
    for name, column, target in _FKS:
        op.drop_constraint(name, _TABLE, type_="foreignkey")
        op.create_foreign_key(name, _TABLE, target, [column], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    for name, column, target in _FKS:
        op.drop_constraint(name, _TABLE, type_="foreignkey")
        op.create_foreign_key(name, _TABLE, target, [column], ["id"])
