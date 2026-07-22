from fastapi import Request
from sqladmin import BaseView, expose
from starlette.responses import HTMLResponse, RedirectResponse

from src.config.admin.categories import CATEGORY_SYNC
from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_async_session
from src.services.sync.service import SyncReportService

log = LoggerProvider().get_logger(__name__)


def _redirect_back(request: Request) -> RedirectResponse:
    referer = request.headers.get("Referer")
    return RedirectResponse(referer or "/admin", status_code=303)


async def _run(request: Request, label: str, action):
    try:
        async with get_async_session() as db:
            service = SyncReportService(db)
            counts = await action(service)
        log.info(f"Sync {label} completed: {counts}")
    except Exception as err:
        log.error(f"Sync {label} failed: {err}", exc_info=True)
        return HTMLResponse(f"Ошибка синхронизации ({label}): {err}", status_code=500)
    return _redirect_back(request)


class SyncActionsAdmin(BaseView):
    category = CATEGORY_SYNC
    name = "Синхронизация с Рапортом"
    name_plural = "Синхронизация с Рапортом"
    icon = "fa-solid fa-rotate"

    @expose(path="/sync", methods=["GET"])
    async def main_sync_page(self, request: Request):
        return await self.templates.TemplateResponse(request, "admin/sync_page.html")

    @expose(path="/sync/action/all", methods=["POST"])
    async def sync_all(self, request: Request):
        return await _run(request, "all", lambda s: s.sync())

    @expose(path="/sync/action/objects", methods=["POST"])
    async def sync_objects(self, request: Request):
        form = await request.form()
        project_raport_id = (form.get("project_raport_id") or "").strip() or None
        return await _run(request, "objects", lambda s: s.sync_objects(project_raport_id=project_raport_id))

    @expose(path="/sync/action/work-catalog", methods=["POST"])
    async def sync_work_catalog(self, request: Request):
        return await _run(request, "work_catalog", lambda s: s.sync_work_catalog())

    @expose(path="/sync/action/contractors", methods=["POST"])
    async def sync_contractors(self, request: Request):
        return await _run(request, "contractors", lambda s: s.sync_contractors())

    @expose(path="/sync/action/contracts", methods=["POST"])
    async def sync_contracts(self, request: Request):
        return await _run(request, "contracts", lambda s: s.sync_contracts())

    @expose(path="/sync/action/users", methods=["POST"])
    async def sync_users(self, request: Request):
        return await _run(request, "users", lambda s: s.sync_users())

    @expose(path="/sync/action/assignments", methods=["POST"])
    async def sync_assignments(self, request: Request):
        form = await request.form()
        housing_raport_id = (form.get("housing_raport_id") or "").strip() or None
        return await _run(
            request,
            "assignments",
            lambda s: s.sync_assignments(housing_raport_id=housing_raport_id),
        )

    @expose(path="/sync/action/tech-sequence", methods=["POST"])
    async def sync_tech_sequence(self, request: Request):
        form = await request.form()
        housing_raport_id = (form.get("housing_raport_id") or "").strip()
        if not housing_raport_id:
            return HTMLResponse("housing_raport_id обязателен для тех. последовательности", status_code=400)
        return await _run(
            request,
            "tech_sequence",
            lambda s: s.sync_tech_sequence(housing_raport_id=housing_raport_id),
        )
