from src.config.admin.categories import CATEGORY_RECONCILIATION
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.reconciliation import DailySummary, ReconciliationResult


class ReconciliationResultAdmin(BaseAdmin, model=ReconciliationResult):  # type: ignore[call-arg]
    category = CATEGORY_RECONCILIATION
    name = "Результат сверки"
    name_plural = "Результаты сверки"
    icon = "fa-solid fa-scale-balanced"

    column_list = [
        ReconciliationResult.id,
        ReconciliationResult.date,
        ReconciliationResult.housing,
        ReconciliationResult.section,
        ReconciliationResult.floor,
        ReconciliationResult.work,
        ReconciliationResult.status,
        ReconciliationResult.pattern,
        ReconciliationResult.fact_percent,
    ]
    column_details_list = [
        ReconciliationResult.id,
        ReconciliationResult.date,
        ReconciliationResult.housing,
        ReconciliationResult.section,
        ReconciliationResult.floor,
        ReconciliationResult.work,
        ReconciliationResult.contractor,
        ReconciliationResult.source_percent,
        ReconciliationResult.fact_percent,
        ReconciliationResult.status,
        ReconciliationResult.pattern,
        ReconciliationResult.plan_item,
        ReconciliationResult.work_fact,
        ReconciliationResult.fact_submitted_at,
        ReconciliationResult.fact_is_late,
        ReconciliationResult.created_at,
    ]
    form_columns = [
        ReconciliationResult.date,
        ReconciliationResult.status,
        ReconciliationResult.pattern,
        ReconciliationResult.fact_is_late,
    ]
    # contractor / plan_item / work_fact are nullable — ids only for those.
    column_searchable_list = [
        ReconciliationResult.date,
        ReconciliationResult.housing_id,
        ReconciliationResult.section_id,
        ReconciliationResult.floor_id,
        ReconciliationResult.work_id,
        ReconciliationResult.contractor_id,
        ReconciliationResult.plan_item_id,
        ReconciliationResult.work_fact_id,
        "housing.name",
        "work.name",
        ReconciliationResult.status,
        ReconciliationResult.pattern,
    ]
    column_sortable_list = [ReconciliationResult.date, ReconciliationResult.status]
    column_default_sort = [("date", True)]


class DailySummaryAdmin(BaseAdmin, model=DailySummary):  # type: ignore[call-arg]
    category = CATEGORY_RECONCILIATION
    name = "Дневная сводка"
    name_plural = "Дневные сводки"
    icon = "fa-solid fa-chart-column"

    column_list = [
        DailySummary.id,
        DailySummary.date,
        DailySummary.housing,
        DailySummary.total_planned,
        DailySummary.total_done_full,
        DailySummary.total_done_partial,
        DailySummary.total_not_done,
        DailySummary.total_no_report,
        DailySummary.total_unplanned,
        DailySummary.completion_rate,
        DailySummary.submission_rate,
    ]
    form_columns = [
        DailySummary.date,
        DailySummary.completion_rate,
        DailySummary.submission_rate,
    ]
    column_searchable_list = [DailySummary.date, DailySummary.housing_id, "housing.name"]
    column_sortable_list = [DailySummary.date, DailySummary.completion_rate]
    column_default_sort = [("date", True)]
