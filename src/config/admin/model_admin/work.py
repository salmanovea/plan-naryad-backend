from src.config.admin.categories import CATEGORY_WORK_CATALOG
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.work import Work, WorkGroup, WorkSet, WorkType


class WorkSetAdmin(BaseAdmin, model=WorkSet):  # type: ignore[call-arg]
    category = CATEGORY_WORK_CATALOG
    name = "Этап"
    name_plural = "Этапы"
    icon = "fa-solid fa-layer-group"

    column_list = [
        WorkSet.id,
        WorkSet.name,
        WorkSet.code,
        WorkSet.order,
        WorkSet.raport_id,
    ]
    column_details_list = [
        WorkSet.id,
        WorkSet.name,
        WorkSet.code,
        WorkSet.order,
        WorkSet.description,
        WorkSet.raport_id,
    ]
    form_columns = [
        WorkSet.name,
        WorkSet.code,
        WorkSet.order,
        WorkSet.description,
        WorkSet.raport_id,
    ]
    column_searchable_list = [WorkSet.name, WorkSet.code, WorkSet.raport_id]
    column_sortable_list = [WorkSet.order, WorkSet.name, WorkSet.code]


class WorkGroupAdmin(BaseAdmin, model=WorkGroup):  # type: ignore[call-arg]
    category = CATEGORY_WORK_CATALOG
    name = "Комплекс"
    name_plural = "Комплексы"
    icon = "fa-solid fa-folder"

    column_list = [
        WorkGroup.id,
        WorkGroup.work_set,
        WorkGroup.name,
        WorkGroup.code,
        WorkGroup.order,
        WorkGroup.raport_id,
    ]
    column_details_list = [
        WorkGroup.id,
        WorkGroup.work_set,
        WorkGroup.name,
        WorkGroup.code,
        WorkGroup.order,
        WorkGroup.description,
        WorkGroup.raport_id,
    ]
    form_columns = [
        WorkGroup.work_set,
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
    icon = "fa-solid fa-sitemap"

    column_list = [
        WorkType.id,
        WorkType.work_group,
        WorkType.name,
        WorkType.code,
        WorkType.order,
        WorkType.raport_id,
    ]
    column_details_list = [
        WorkType.id,
        WorkType.work_group,
        WorkType.name,
        WorkType.code,
        WorkType.order,
        WorkType.description,
        WorkType.raport_id,
    ]
    form_columns = [
        WorkType.work_group,
        WorkType.name,
        WorkType.code,
        WorkType.order,
        WorkType.description,
        WorkType.raport_id,
    ]
    column_searchable_list = [WorkType.name, WorkType.code, WorkType.raport_id]
    column_sortable_list = [WorkType.order, WorkType.name, WorkType.code]


class WorkAdmin(BaseAdmin, model=Work):  # type: ignore[call-arg]
    category = CATEGORY_WORK_CATALOG
    name = "Работа"
    name_plural = "Работы"
    icon = "fa-solid fa-hammer"

    column_list = [
        Work.id,
        Work.work_type,
        Work.name,
        Work.code,
        Work.unit,
        Work.raport_id,
    ]
    column_details_list = [
        Work.id,
        Work.work_type,
        Work.name,
        Work.code,
        Work.unit,
        Work.description,
        Work.raport_id,
    ]
    form_columns = [
        Work.work_type,
        Work.name,
        Work.code,
        Work.unit,
        Work.description,
        Work.raport_id,
    ]
    column_searchable_list = [Work.name, Work.code, Work.raport_id]
    column_sortable_list = [Work.name, Work.code]
