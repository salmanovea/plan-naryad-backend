from src.config.admin.categories import CATEGORY_PLAN
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.plan import PlanItem
from src.models.dbo.tables.settings import ContractorFloorLimit
from src.models.dbo.tables.work import TechSequenceItem


class PlanItemAdmin(BaseAdmin, model=PlanItem):  # type: ignore[call-arg]
    category = CATEGORY_PLAN
    name = "Позиция план-наряда"
    name_plural = "Позиции план-наряда"
    icon = "fa-solid fa-list-check"

    column_list = [
        PlanItem.id,
        PlanItem.date,
        PlanItem.housing_id,
        PlanItem.section_id,
        PlanItem.floor_id,
        PlanItem.work_id,
        PlanItem.contractor_id,
        PlanItem.status,
        PlanItem.source,
        PlanItem.rs_confirmed,
    ]
    column_details_list = [
        PlanItem.id,
        PlanItem.date,
        PlanItem.housing_id,
        PlanItem.section_id,
        PlanItem.floor_id,
        PlanItem.work_id,
        PlanItem.contractor_id,
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
    column_searchable_list = [PlanItem.rs_confirmed_by]
    column_sortable_list = [PlanItem.date, PlanItem.status]
    column_default_sort = [("date", True)]


class TechSequenceItemAdmin(BaseAdmin, model=TechSequenceItem):  # type: ignore[call-arg]
    category = CATEGORY_PLAN
    name = "Техпоследовательность"
    name_plural = "Техпоследовательность"
    icon = "fa-solid fa-diagram-project"

    column_list = [
        TechSequenceItem.id,
        TechSequenceItem.housing_id,
        TechSequenceItem.section_id,
        TechSequenceItem.work_id,
        TechSequenceItem.order,
        TechSequenceItem.floor_sorting_direction,
        TechSequenceItem.source,
    ]
    column_details_list = [
        TechSequenceItem.id,
        TechSequenceItem.housing_id,
        TechSequenceItem.section_id,
        TechSequenceItem.work_id,
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
    column_sortable_list = [TechSequenceItem.order]
    column_default_sort = [("order", False)]


class ContractorFloorLimitAdmin(BaseAdmin, model=ContractorFloorLimit):  # type: ignore[call-arg]
    category = CATEGORY_PLAN
    name = "Лимит этажей"
    name_plural = "Лимиты этажей (Р8)"
    icon = "fa-solid fa-arrow-up-9-1"

    column_list = [
        ContractorFloorLimit.id,
        ContractorFloorLimit.contractor,
        ContractorFloorLimit.work,
        ContractorFloorLimit.floors_limit,
    ]
    form_columns = [
        ContractorFloorLimit.contractor,
        ContractorFloorLimit.work,
        ContractorFloorLimit.floors_limit,
    ]
    column_sortable_list = [ContractorFloorLimit.floors_limit]
