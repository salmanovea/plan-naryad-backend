"""Align schema naming with Raport (decisions Р0, Р1, Р6a, Р6b, Р8).

Written by hand on purpose: autogenerate cannot see renames and would emit
drop + create, destroying the data.

Order matters:
  1. drop the operational contractor_assignments — frees the name (Р1)
  2. shift the work hierarchy down one level: work_types → works,
     work_groups → work_types, then create the new upper levels
  3. project hierarchy: wf_projects → projects, wf_project_objects →
     construction_objects, new queues
  4. drop the wf_ prefix from the remaining workforce tables
  5. rename FK columns and their constraints
  6. new columns and tables (plan snapshot fields, floor limits, action log)

Revision ID: b7f1c02e9a34
Revises: a1b2c3d4e5f6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7f1c02e9a34"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (old table, new table)
WF_TABLE_RENAMES = [
    ("wf_projects", "projects"),
    ("wf_project_objects", "construction_objects"),
    ("wf_norms", "headcount_norms"),
    ("wf_budget_periods", "budget_periods"),
    ("wf_budget_items", "budget_items"),
    ("wf_article_mapping", "article_bdr_works"),
    ("wf_headcount_facts", "headcount_facts"),
    ("wf_headcount_plans", "headcount_plans"),
    ("wf_contractor_assignments", "contractor_assignments"),
    ("wf_challenges", "challenges"),
    ("wf_challenge_items", "challenge_items"),
    ("wf_mobilization_plans", "mobilization_plans"),
    ("wf_mobilization_checkpoints", "mobilization_checkpoints"),
    ("wf_violations", "violations"),
]

# Tables whose work_type_id points at the catalogue leaf and becomes work_id.
WORK_ID_TABLES = [
    "work_facts",
    "plan_items",
    "reconciliation_results",
    "tech_sequence_items",
    "headcount_norms",
    "article_bdr_works",
    "budget_items",
    "headcount_facts",
    "headcount_plans",
    "contractor_assignments",
    "challenge_items",
    "violations",
]

# Tables where the construction-object FK was called object_id.
OBJECT_ID_TABLES = [
    "budget_items",
    "headcount_facts",
    "headcount_plans",
    "contractor_assignments",
    "challenges",
    "violations",
]


def _rename_table_objects(old: str, new: str) -> None:
    """Re-point indexes and constraints at the new table name.

    `ALTER TABLE ... RENAME TO` leaves every index and constraint carrying the old
    name, which then collides with anything new that legitimately wants it — exactly
    what happens here, where `work_groups` is reused for a different level.
    """
    op.execute(
        f"""
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT indexname FROM pg_indexes
                WHERE schemaname = current_schema() AND tablename = '{new}'
                  AND indexname LIKE '%{old}%'
            LOOP
                EXECUTE format('ALTER INDEX %I RENAME TO %I',
                               r.indexname, replace(r.indexname, '{old}', '{new}'));
            END LOOP;
            FOR r IN
                SELECT conname FROM pg_constraint WHERE conrelid = '{new}'::regclass
                  AND conname LIKE '%{old}%'
            LOOP
                EXECUTE format('ALTER TABLE {new} RENAME CONSTRAINT %I TO %I',
                               r.conname, replace(r.conname, '{old}', '{new}'));
            END LOOP;
        END $$;
        """
    )


def upgrade() -> None:
    # ── 1. Operational assignments are gone: read from Raport instead (Р1) ────
    op.drop_table("contractor_assignments")

    # ── 2. Work hierarchy shifts down one level (Р6b) ─────────────────────────
    # Order matters: freeing the `work_types` names before work_groups claims them.
    op.rename_table("work_types", "works")
    _rename_table_objects("work_types", "works")
    op.rename_table("work_groups", "work_types")
    _rename_table_objects("work_groups", "work_types")

    op.alter_column("works", "group_id", new_column_name="work_type_id")
    op.execute("ALTER INDEX IF EXISTS ix_works_group_id RENAME TO ix_works_work_type_id")
    op.execute("ALTER TABLE works RENAME CONSTRAINT fk_works_group_id TO fk_works_work_type_id")

    op.create_table(
        "work_sets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("raport_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("code", name="uq_work_sets_code"),
    )
    op.create_index("ix_work_sets_raport_id", "work_sets", ["raport_id"], unique=True)

    op.create_table(
        "work_groups",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("raport_id", sa.String(length=255), nullable=True),
        sa.Column("work_set_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["work_set_id"], ["work_sets.id"], name="fk_work_groups_work_set_id"),
        sa.UniqueConstraint("code", name="uq_work_groups_code"),
    )
    op.create_index("ix_work_groups_work_set_id", "work_groups", ["work_set_id"])
    op.create_index("ix_work_groups_raport_id", "work_groups", ["raport_id"], unique=True)

    # The old work_groups carried no unit; the new work_types level does not either.
    op.add_column("work_types", sa.Column("work_group_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_work_types_work_group_id", "work_types", "work_groups", ["work_group_id"], ["id"])
    op.create_index("ix_work_types_work_group_id", "work_types", ["work_group_id"])

    # ── 3. Project hierarchy (Р6b) ────────────────────────────────────────────
    for old, new in WF_TABLE_RENAMES:
        op.rename_table(old, new)
        _rename_table_objects(old, new)

    op.create_table(
        "queues",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("raport_id", sa.String(length=255), nullable=True),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_queues_project_id"),
    )
    op.create_index("ix_queues_project_id", "queues", ["project_id"])
    op.create_index("ix_queues_raport_id", "queues", ["raport_id"], unique=True)

    op.add_column("construction_objects", sa.Column("queue_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_construction_objects_queue_id", "construction_objects", "queues", ["queue_id"], ["id"])
    op.create_index("ix_construction_objects_queue_id", "construction_objects", ["queue_id"])

    # ── 4. FK column renames (indexes do not follow a column rename) ──────────
    for table in WORK_ID_TABLES:
        op.alter_column(table, "work_type_id", new_column_name="work_id")
        op.execute(f"ALTER INDEX IF EXISTS ix_{table}_work_type_id RENAME TO ix_{table}_work_id")
    for table in OBJECT_ID_TABLES:
        op.alter_column(table, "object_id", new_column_name="construction_object_id")
        op.execute(f"ALTER INDEX IF EXISTS ix_{table}_object_id RENAME TO ix_{table}_construction_object_id")

    # ── 5. Plan items: percent snapshot replaces volumes (Р0, Р6) ─────────────
    op.add_column("plan_items", sa.Column("source_percent", sa.Numeric(6, 2), nullable=True))
    op.add_column("plan_items", sa.Column("work_cell_contractor_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("plan_items", sa.Column("work_cell_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_plan_items_work_cell_contractor_id", "plan_items", ["work_cell_contractor_id"])
    op.create_index("ix_plan_items_work_cell_id", "plan_items", ["work_cell_id"])
    op.alter_column("plan_items", "planned_volume", nullable=True)
    op.alter_column("plan_items", "unit", nullable=True)

    # ── 6. Work facts mirror Raport naming (Р5) ───────────────────────────────
    op.alter_column("work_facts", "date", new_column_name="work_date")
    op.execute("ALTER INDEX IF EXISTS ix_work_facts_date RENAME TO ix_work_facts_work_date")
    op.alter_column("work_facts", "actual_volume", new_column_name="volume")
    op.add_column("work_facts", sa.Column("percent", sa.Numeric(6, 2), nullable=True))
    op.add_column("work_facts", sa.Column("work_cell_contractor_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("work_facts", sa.Column("work_cell_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_work_facts_work_cell_contractor_id", "work_facts", ["work_cell_contractor_id"])
    op.create_index("ix_work_facts_work_cell_id", "work_facts", ["work_cell_id"])

    # ── 7. Reconciliation percent columns (Р5) ────────────────────────────────
    op.add_column("reconciliation_results", sa.Column("source_percent", sa.Numeric(6, 2), nullable=True))
    op.add_column("reconciliation_results", sa.Column("fact_percent", sa.Numeric(6, 2), nullable=True))

    # ── 8. Tech sequence gets the plan-template floor settings (Р6a) ──────────
    op.add_column("tech_sequence_items", sa.Column("planning_type", sa.String(length=20), nullable=True))
    op.add_column("tech_sequence_items", sa.Column("floor_sorting_direction", sa.String(length=4), nullable=True))
    op.add_column("tech_sequence_items", sa.Column("lag_between_floors", sa.Integer(), nullable=True))

    # ── 9. New tables (Р8 and the action journal) ─────────────────────────────
    op.create_table(
        "contractor_floor_limits",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("contractor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("work_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("floors_limit", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"], name="fk_contractor_floor_limits_contractor_id"),
        sa.ForeignKeyConstraint(["work_id"], ["works.id"], name="fk_contractor_floor_limits_work_id"),
    )
    op.create_index("ix_contractor_floor_limits_contractor_id", "contractor_floor_limits", ["contractor_id"])
    op.create_index("ix_contractor_floor_limits_work_id", "contractor_floor_limits", ["work_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_contractor_floor_limits_key "
        "ON contractor_floor_limits (contractor_id, work_id) NULLS NOT DISTINCT"
    )

    op.create_table(
        "action_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_action_logs_action", "action_logs", ["action"])
    op.create_index("ix_action_logs_entity_id", "action_logs", ["entity_id"])
    op.create_index("ix_action_logs_created_at", "action_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("action_logs")
    op.drop_table("contractor_floor_limits")

    op.drop_column("tech_sequence_items", "lag_between_floors")
    op.drop_column("tech_sequence_items", "floor_sorting_direction")
    op.drop_column("tech_sequence_items", "planning_type")

    op.drop_column("reconciliation_results", "fact_percent")
    op.drop_column("reconciliation_results", "source_percent")

    op.drop_index("ix_work_facts_work_cell_id", table_name="work_facts")
    op.drop_index("ix_work_facts_work_cell_contractor_id", table_name="work_facts")
    op.drop_column("work_facts", "work_cell_id")
    op.drop_column("work_facts", "work_cell_contractor_id")
    op.drop_column("work_facts", "percent")
    op.alter_column("work_facts", "volume", new_column_name="actual_volume")
    op.execute("ALTER INDEX IF EXISTS ix_work_facts_work_date RENAME TO ix_work_facts_date")
    op.alter_column("work_facts", "work_date", new_column_name="date")

    op.alter_column("plan_items", "unit", nullable=False)
    op.alter_column("plan_items", "planned_volume", nullable=False)
    op.drop_index("ix_plan_items_work_cell_id", table_name="plan_items")
    op.drop_index("ix_plan_items_work_cell_contractor_id", table_name="plan_items")
    op.drop_column("plan_items", "work_cell_id")
    op.drop_column("plan_items", "work_cell_contractor_id")
    op.drop_column("plan_items", "source_percent")

    for table in OBJECT_ID_TABLES:
        op.alter_column(table, "construction_object_id", new_column_name="object_id")
        op.execute(f"ALTER INDEX IF EXISTS ix_{table}_construction_object_id RENAME TO ix_{table}_object_id")
    for table in WORK_ID_TABLES:
        op.alter_column(table, "work_id", new_column_name="work_type_id")
        op.execute(f"ALTER INDEX IF EXISTS ix_{table}_work_id RENAME TO ix_{table}_work_type_id")

    op.drop_index("ix_construction_objects_queue_id", table_name="construction_objects")
    op.drop_constraint("fk_construction_objects_queue_id", "construction_objects", type_="foreignkey")
    op.drop_column("construction_objects", "queue_id")
    op.drop_table("queues")

    for old, new in reversed(WF_TABLE_RENAMES):
        op.rename_table(new, old)
        _rename_table_objects(new, old)

    op.drop_index("ix_work_types_work_group_id", table_name="work_types")
    op.drop_constraint("fk_work_types_work_group_id", "work_types", type_="foreignkey")
    op.drop_column("work_types", "work_group_id")
    op.drop_table("work_groups")
    op.drop_table("work_sets")

    op.execute("ALTER TABLE works RENAME CONSTRAINT fk_works_work_type_id TO fk_works_group_id")
    op.execute("ALTER INDEX IF EXISTS ix_works_work_type_id RENAME TO ix_works_group_id")
    op.alter_column("works", "work_type_id", new_column_name="group_id")

    op.rename_table("work_types", "work_groups")
    _rename_table_objects("work_types", "work_groups")
    op.rename_table("works", "work_types")
    _rename_table_objects("works", "work_types")

    op.create_table(
        "contractor_assignments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("contractor_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("housing_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("section_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("work_group_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("work_type_ids", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"], name="fk_contractor_assignments_contractor_id"),
        sa.ForeignKeyConstraint(["housing_id"], ["housings.id"], name="fk_contractor_assignments_housing_id"),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"], name="fk_contractor_assignments_section_id"),
        sa.ForeignKeyConstraint(["work_group_id"], ["work_groups.id"], name="fk_contractor_assignments_work_group_id"),
    )
