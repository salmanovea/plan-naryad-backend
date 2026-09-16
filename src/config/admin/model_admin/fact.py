from src.config.admin.categories import CATEGORY_RECONCILIATION
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.fact import WorkFact


class WorkFactAdmin(BaseAdmin, model=WorkFact):  # type: ignore[call-arg]
    category = CATEGORY_RECONCILIATION
    name = "Факт работы"
    name_plural = "Факты работ"
    icon = "fa-solid fa-clipboard-check"

    column_list = [
        WorkFact.id,
        WorkFact.work_date,
        WorkFact.housing,
        WorkFact.section,
        WorkFact.floor,
        WorkFact.work,
        WorkFact.contractor,
        WorkFact.percent,
        WorkFact.source,
    ]
    column_details_list = [
        WorkFact.id,
        WorkFact.work_date,
        WorkFact.housing,
        WorkFact.section,
        WorkFact.floor,
        WorkFact.work,
        WorkFact.contractor,
        WorkFact.volume,
        WorkFact.percent,
        WorkFact.unit,
        WorkFact.work_cell_contractor_id,
        WorkFact.work_cell_id,
        WorkFact.submitted_at,
        WorkFact.submitted_by,
        WorkFact.source,
        WorkFact.comment,
        WorkFact.raport_id,
    ]
    form_columns = [
        WorkFact.work_date,
        WorkFact.housing,
        WorkFact.section,
        WorkFact.floor,
        WorkFact.work,
        WorkFact.contractor,
        WorkFact.volume,
        WorkFact.percent,
        WorkFact.source,
    ]
    # contractor is nullable (Raport rarely attributes facts) — id only.
    column_searchable_list = [
        WorkFact.work_date,
        WorkFact.housing_id,
        WorkFact.section_id,
        WorkFact.floor_id,
        WorkFact.work_id,
        WorkFact.contractor_id,
        "housing.name",
        "work.name",
        WorkFact.submitted_by,
        WorkFact.raport_id,
    ]
    column_sortable_list = [WorkFact.work_date, WorkFact.percent]
    column_default_sort = [("work_date", True)]
