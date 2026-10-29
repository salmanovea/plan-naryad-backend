from typing import Any

from starlette.requests import Request

from src.config.admin.categories import CATEGORY_PLAN
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.plan import PlanItem
from src.models.dbo.tables.settings import NIGHTLY_PLAN_TIME, ContractorPositionLimit, PlanSettings
from src.models.dbo.tables.work import TechSequenceItem


class PlanItemAdmin(BaseAdmin, model=PlanItem):  # type: ignore[call-arg]
    category = CATEGORY_PLAN
    name = "Позиция план-наряда"
    name_plural = "Позиции план-наряда"
    icon = "fa-solid fa-list-check"

    column_list = [
        PlanItem.id,
        PlanItem.date,
        PlanItem.housing,
        PlanItem.section,
        PlanItem.floor,
        PlanItem.work,
        PlanItem.contractor,
        PlanItem.status,
        PlanItem.source,
        PlanItem.rs_confirmed,
    ]
    column_details_list = [
        PlanItem.id,
        PlanItem.date,
        PlanItem.housing,
        PlanItem.section,
        PlanItem.floor,
        PlanItem.work,
        PlanItem.contractor,
        PlanItem.source_percent,
        PlanItem.work_cell_contractor_id,
        PlanItem.work_cell_id,
        PlanItem.status,
        PlanItem.source,
        PlanItem.rs_confirmed,
        PlanItem.rs_confirmed_at,
        PlanItem.rs_confirmed_by,
    ]
    form_columns = [
        PlanItem.date,
        PlanItem.housing,
        PlanItem.section,
        PlanItem.status,
        PlanItem.source,
        PlanItem.rs_confirmed,
    ]
    # UUIDs and dates are searchable too: sqladmin casts every field to text before
    # the ILIKE. Dotted paths join the relation — INNER JOIN, so only non-nullable ones.
    column_searchable_list = [
        PlanItem.date,
        PlanItem.housing_id,
        PlanItem.section_id,
        PlanItem.floor_id,
        PlanItem.work_id,
        PlanItem.contractor_id,
        "housing.name",
        "work.name",
        "contractor.name",
        PlanItem.status,
        PlanItem.rs_confirmed_by,
    ]
    column_sortable_list = [PlanItem.date, PlanItem.status]
    column_default_sort = [("date", True)]


class TechSequenceItemAdmin(BaseAdmin, model=TechSequenceItem):  # type: ignore[call-arg]
    category = CATEGORY_PLAN
    name = "Техпоследовательность"
    name_plural = "Техпоследовательность"
    icon = "fa-solid fa-diagram-project"

    column_list = [
        TechSequenceItem.id,
        TechSequenceItem.housing,
        TechSequenceItem.section,
        TechSequenceItem.work,
        TechSequenceItem.order,
        TechSequenceItem.floor_sorting_direction,
        TechSequenceItem.source,
    ]
    column_details_list = [
        TechSequenceItem.id,
        TechSequenceItem.housing,
        TechSequenceItem.section,
        TechSequenceItem.work,
        TechSequenceItem.order,
        TechSequenceItem.depends_on,
        TechSequenceItem.depends_on_ss,
        TechSequenceItem.lag_days,
        TechSequenceItem.planning_type,
        TechSequenceItem.floor_sorting_direction,
        TechSequenceItem.lag_between_floors,
        TechSequenceItem.estimated_days,
        TechSequenceItem.source,
    ]
    form_columns = [
        TechSequenceItem.housing,
        TechSequenceItem.section,
        TechSequenceItem.work,
        TechSequenceItem.order,
        TechSequenceItem.floor_sorting_direction,
        TechSequenceItem.source,
    ]
    # section is nullable (housing-wide rows) — id only, a dotted join would hide them.
    column_searchable_list = [
        TechSequenceItem.housing_id,
        TechSequenceItem.section_id,
        TechSequenceItem.work_id,
        "housing.name",
        "work.name",
    ]
    column_sortable_list = [TechSequenceItem.order]
    column_default_sort = [("order", False)]


class ContractorPositionLimitAdmin(BaseAdmin, model=ContractorPositionLimit):  # type: ignore[call-arg]
    category = CATEGORY_PLAN
    name = "Лимит позиций подрядчика"
    name_plural = "Лимиты позиций (Р8)"
    icon = "fa-solid fa-arrow-up-9-1"

    column_list = [
        ContractorPositionLimit.id,
        ContractorPositionLimit.contractor,
        ContractorPositionLimit.positions_limit,
    ]
    form_columns = [
        ContractorPositionLimit.contractor,
        ContractorPositionLimit.positions_limit,
    ]
    column_searchable_list = [
        ContractorPositionLimit.contractor_id,
        "contractor.name",
    ]
    column_sortable_list = [ContractorPositionLimit.positions_limit]


class PlanSettingsAdmin(BaseAdmin, model=PlanSettings):  # type: ignore[call-arg]
    """The single settings row: created by the migration, only ever edited."""

    category = CATEGORY_PLAN
    name = "Настройки план-наряда"
    name_plural = "Настройки план-наряда"
    icon = "fa-solid fa-clock"

    can_create = False
    can_delete = False

    column_list = [PlanSettings.transfer_time]
    column_details_list = [PlanSettings.transfer_time]
    form_columns = [PlanSettings.transfer_time]
    column_labels = {PlanSettings.transfer_time: "Время передачи заданий подрядчику (МСК)"}

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        """The nightly job builds today's plan only while today is open, so the transfer has to follow it."""
        transfer_time = data.get("transfer_time")
        if transfer_time is not None and transfer_time <= NIGHTLY_PLAN_TIME:
            raise ValueError(
                f"Время передачи должно быть позже {NIGHTLY_PLAN_TIME:%H:%M} — "
                "в это время ночная генерация строит план-наряд на текущий день."
            )
