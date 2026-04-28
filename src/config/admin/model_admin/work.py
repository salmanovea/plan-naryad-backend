from src.config.admin.categories import CATEGORY_WORK_CATALOG
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.work import WorkGroup, WorkType


class WorkGroupAdmin(BaseAdmin, model=WorkGroup):  # type: ignore[call-arg]
    category = CATEGORY_WORK_CATALOG
    name = "Группа работ"
    name_plural = "Группы работ"
    icon = "fa-solid fa-folder"

    column_list = [
        WorkGroup.id,
        WorkGroup.name,
        WorkGroup.code,
        WorkGroup.order,
        WorkGroup.raport_id,
    ]
    column_details_list = [
        WorkGroup.id,
        WorkGroup.name,
        WorkGroup.code,
        WorkGroup.order,
        WorkGroup.description,
        WorkGroup.raport_id,
    ]
    form_columns = [
        WorkGroup.name,
        WorkGroup.code,
        WorkGroup.order,
        WorkGroup.description,
        WorkGroup.raport_id,
    ]
    column_searchable_list = [WorkGroup.name, WorkGroup.code, WorkGroup.raport_id]
    column_sortable_list = [WorkGroup.order, WorkGroup.name, WorkGroup.code]


class WorkTypeAdmin(BaseAdmin, model=WorkType):  # type: ignore[call-arg]
    category = CATEGORY_WORK_CATALOG
    name = "Вид работ"
    name_plural = "Виды работ"
    icon = "fa-solid fa-hammer"

    column_list = [
        WorkType.id,
        WorkType.group,
        WorkType.name,
        WorkType.code,
        WorkType.unit,
        WorkType.raport_id,
    ]
    column_details_list = [
        WorkType.id,
        WorkType.group,
        WorkType.name,
        WorkType.code,
        WorkType.unit,
        WorkType.description,
        WorkType.raport_id,
    ]
    form_columns = [
        WorkType.group,
        WorkType.name,
        WorkType.code,
        WorkType.unit,
        WorkType.description,
        WorkType.raport_id,
    ]
    column_searchable_list = [WorkType.name, WorkType.code, WorkType.raport_id]
    column_sortable_list = [WorkType.name, WorkType.code]
