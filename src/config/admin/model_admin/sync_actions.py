from fastapi import Request
from sqladmin import BaseView, expose
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from src.config.admin.categories import CATEGORY_SYNC
from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_async_session
from src.services.sync.service import SyncService

log = LoggerProvider().get_logger(__name__)

_templates = Jinja2Templates(directory="templates")


class SyncActionsAdmin(BaseView):
    category = CATEGORY_SYNC
    name = "Синхронизация с Рапортом"
    name_plural = "Синхронизация с Рапортом"
    icon = "fa-solid fa-rotate"

    @expose(path="/sync", methods=["GET"])
    async def sync_page(self, request: Request):
        return _templates.TemplateResponse("admin/sync_page.html", {"request": request})

    @expose(path="/sync/action/objects", methods=["POST"])
    async def sync_objects(self, request: Request):
        try:
            async with get_async_session() as db:
                service = SyncService(db)
                counts = await service.sync_objects()
            log.info(f"Sync objects completed: {counts}")
        except Exception as err:
            log.error(f"Sync objects failed: {err}", exc_info=True)
            return HTMLResponse(f"Ошибка синхронизации объектов: {err}", status_code=500)

        referer = request.headers.get("Referer")
        return RedirectResponse(referer or "/admin", status_code=303)

    @expose(path="/sync/action/work-catalog", methods=["POST"])
    async def sync_work_catalog(self, request: Request):
        try:
            async with get_async_session() as db:
                service = SyncService(db)
                counts = await service.sync_work_catalog()
            log.info(f"Sync work catalog completed: {counts}")
        except Exception as err:
            log.error(f"Sync work catalog failed: {err}", exc_info=True)
            return HTMLResponse(f"Ошибка синхронизации каталога работ: {err}", status_code=500)

        referer = request.headers.get("Referer")
        return RedirectResponse(referer or "/admin", status_code=303)

    @expose(path="/sync/action/contractors", methods=["POST"])
    async def sync_contractors(self, request: Request):
        try:
            async with get_async_session() as db:
                service = SyncService(db)
                counts = await service.sync_contractors()
            log.info(f"Sync contractors completed: {counts}")
        except Exception as err:
            log.error(f"Sync contractors failed: {err}", exc_info=True)
            return HTMLResponse(f"Ошибка синхронизации подрядчиков: {err}", status_code=500)

        referer = request.headers.get("Referer")
        return RedirectResponse(referer or "/admin", status_code=303)
