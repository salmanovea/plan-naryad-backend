from fastapi import Request
from sqladmin import action
from starlette.responses import RedirectResponse, Response

from src.config.admin.categories import CATEGORY_WORKFORCE
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.config.postgres.db_config import get_async_session
from src.models.dbo.tables.workforce import WfProject, WfProjectObject
from src.services.sync.service import SyncService


class WfProjectAdmin(BaseAdmin, model=WfProject):  # type: ignore[call-arg]
    category = CATEGORY_WORKFORCE
    name = "Проект"
    name_plural = "Проекты"
    icon = "fa-solid fa-city"

    column_list = [
        WfProject.id,
        WfProject.name,
        WfProject.project_class,
        WfProject.raport_id,
    ]
    column_details_list = [
        WfProject.id,
        WfProject.name,
        WfProject.project_class,
        WfProject.description,
        WfProject.raport_id,
    ]
    form_columns = [
        WfProject.name,
        WfProject.project_class,
        WfProject.description,
        WfProject.raport_id,
    ]
    column_searchable_list = [WfProject.name, WfProject.raport_id]
    column_sortable_list = [WfProject.name, WfProject.project_class]

    @action(
        name="sync_objects",
        label="Синхронизировать объекты",
        confirmation_message="Запустить синхронизацию иерархии объектов из Рапорта для выбранных проектов?",
    )
    async def sync_objects(self, request: Request) -> Response:
        pks = request.query_params.get("pks", "").split(",")
        errors = []
        for pk in pks:
            pk = pk.strip()
            if not pk:
                continue
            try:
                async with get_async_session() as db:
                    project = await db.get(WfProject, pk)
                    if not project:
                        continue
                    raport_id = project.raport_id
                    service = SyncService(db)
                    await service.sync_objects(project_raport_id=raport_id)
            except Exception as err:
                errors.append(str(err))

        if errors:
            return Response(content=f"Ошибки при синхронизации: {'; '.join(errors)}", status_code=500)

        referer = request.headers.get("Referer")
        if referer:
            return RedirectResponse(referer, status_code=303)
        return RedirectResponse(
            request.url_for("admin:list", identity=self.identity),
            status_code=303,
        )


class WfProjectObjectAdmin(BaseAdmin, model=WfProjectObject):  # type: ignore[call-arg]
    category = CATEGORY_WORKFORCE
    name = "Объект строительства"
    name_plural = "Объекты строительства"
    icon = "fa-solid fa-building-columns"

    column_list = [
        WfProjectObject.id,
        WfProjectObject.project_id,
        WfProjectObject.name,
        WfProjectObject.planned_end_date,
        WfProjectObject.raport_id,
    ]
    column_details_list = [
        WfProjectObject.id,
        WfProjectObject.project_id,
        WfProjectObject.name,
        WfProjectObject.description,
        WfProjectObject.planned_end_date,
        WfProjectObject.total_budget_remaining,
        WfProjectObject.raport_id,
    ]
    form_columns = [
        WfProjectObject.project_id,
        WfProjectObject.name,
        WfProjectObject.description,
        WfProjectObject.planned_end_date,
        WfProjectObject.total_budget_remaining,
        WfProjectObject.raport_id,
    ]
    column_searchable_list = [WfProjectObject.name, WfProjectObject.raport_id]
    column_sortable_list = [WfProjectObject.name, WfProjectObject.planned_end_date]
