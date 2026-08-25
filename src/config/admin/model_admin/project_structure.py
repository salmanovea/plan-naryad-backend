from fastapi import Request
from sqladmin import action
from starlette.responses import RedirectResponse, Response

from src.config.admin.categories import CATEGORY_PROJECT_STRUCTURE
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.config.postgres.db_config import get_async_session
from src.models.dbo.tables.project_structure import ConstructionObject, Project, Queue
from src.services.sync.service import SyncReportService


class ProjectAdmin(BaseAdmin, model=Project):  # type: ignore[call-arg]
    category = CATEGORY_PROJECT_STRUCTURE
    name = "Проект"
    name_plural = "Проекты"
    icon = "fa-solid fa-city"

    column_list = [
        Project.id,
        Project.name,
        Project.project_class,
        Project.raport_id,
    ]
    column_details_list = [
        Project.id,
        Project.name,
        Project.project_class,
        Project.description,
        Project.raport_id,
    ]
    form_columns = [
        Project.name,
        Project.project_class,
        Project.description,
        Project.raport_id,
    ]
    column_searchable_list = [Project.name, Project.raport_id]
    column_sortable_list = [Project.name, Project.project_class]

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
                    project = await db.get(Project, pk)
                    if not project:
                        continue
                    raport_id = project.raport_id
                    service = SyncReportService(db)
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


class QueueAdmin(BaseAdmin, model=Queue):  # type: ignore[call-arg]
    category = CATEGORY_PROJECT_STRUCTURE
    name = "Очередь"
    name_plural = "Очереди"
    icon = "fa-solid fa-list-ol"

    column_list = [
        Queue.id,
        Queue.project,
        Queue.name,
        Queue.order,
        Queue.raport_id,
    ]
    column_details_list = [
        Queue.id,
        Queue.project,
        Queue.name,
        Queue.order,
        Queue.raport_id,
    ]
    form_columns = [
        Queue.project,
        Queue.name,
        Queue.order,
        Queue.raport_id,
    ]
    column_searchable_list = [Queue.name, Queue.raport_id]
    column_sortable_list = [Queue.order, Queue.name]


class ConstructionObjectAdmin(BaseAdmin, model=ConstructionObject):  # type: ignore[call-arg]
    category = CATEGORY_PROJECT_STRUCTURE
    name = "Объект строительства"
    name_plural = "Объекты строительства"
    icon = "fa-solid fa-building-columns"

    column_list = [
        ConstructionObject.id,
        ConstructionObject.project_id,
        ConstructionObject.queue_id,
        ConstructionObject.name,
        ConstructionObject.planned_end_date,
        ConstructionObject.raport_id,
    ]
    column_details_list = [
        ConstructionObject.id,
        ConstructionObject.project_id,
        ConstructionObject.queue_id,
        ConstructionObject.name,
        ConstructionObject.description,
        ConstructionObject.planned_end_date,
        ConstructionObject.total_budget_remaining,
        ConstructionObject.raport_id,
    ]
    form_columns = [
        ConstructionObject.project,
        ConstructionObject.queue,
        ConstructionObject.name,
        ConstructionObject.description,
        ConstructionObject.planned_end_date,
        ConstructionObject.total_budget_remaining,
        ConstructionObject.raport_id,
    ]
    column_searchable_list = [ConstructionObject.name, ConstructionObject.raport_id]
    column_sortable_list = [ConstructionObject.name, ConstructionObject.planned_end_date]
