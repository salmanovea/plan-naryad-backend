"""
Raport sync service — pulls reference data from Raport and upserts it locally.

Three sync groups:
  A  objects — WfProject → WfProjectObject → Housing → Section → Floor
  B  work_catalog — WorkGroup → WorkType
  C  contractors — Contractor

Plus payload-driven `import_*` variants that accept Pydantic items instead
of calling the live Raport API. Used by offline xlsx dumps; same upsert
logic, same `raport_id` upsert key.
"""

from typing import Any, Iterable
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.sync.schemes import (
    ImportConstructionObjectItem,
    ImportContractorItem,
    ImportFloorItem,
    ImportHousingItem,
    ImportProjectItem,
    ImportSectionItem,
    ImportWorkGroupItem,
    ImportWorkTypeItem,
)
from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_session
from src.external.report.client import ReportClient
from src.models import managers
from src.models.managers.common import BaseManager
from src.services.common import BaseService

log = LoggerProvider().get_logger(__name__)

_PER_PAGE = 200


async def _fetch_all(client: ReportClient, method_name: str, **kwargs: Any) -> list[dict]:
    """Paginate through a Raport list endpoint and return all items."""
    method = getattr(client, method_name)
    page, results = 1, []
    while True:
        resp = await method(page=page, per_page=_PER_PAGE, **kwargs)
        items = resp.get("data", [])
        results.extend(items)
        pagination = resp.get("pagination") or {}
        total = pagination.get("total", len(items))
        if len(results) >= total or not items:
            break
        page += 1
    return results


class SyncService(BaseService):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.wf_project_manager = managers.WfProjectManager(db)
        self.wf_project_object_manager = managers.WfProjectObjectManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.work_group_manager = managers.WorkGroupManager(db)
        self.work_type_manager = managers.WorkTypeManager(db)
        self.contractor_manager = managers.ContractorManager(db)

    # ------------------------------------------------------------------
    # Group A — objects hierarchy
    # ------------------------------------------------------------------

    async def sync_objects(self, project_raport_id: str | None = None) -> dict[str, int]:
        """Sync WfProject → WfProjectObject → Housing → Section → Floor from Raport."""
        client = ReportClient()
        counts: dict[str, int] = {
            "projects": 0,
            "construction_objects": 0,
            "housings": 0,
            "sections": 0,
            "floors": 0,
        }

        raport_projects = await _fetch_all(client, "list_projects")
        if project_raport_id:
            raport_projects = [p for p in raport_projects if str(p["id"]) == project_raport_id]

        for rp in raport_projects:
            rp_id = str(rp["id"])

            project_data = {
                "raport_id": rp_id,
                "name": rp.get("name", ""),
                "description": rp.get("description"),
                "project_class": rp.get("class", "Комфорт"),
            }
            await self.wf_project_manager.bulk_upsert(
                [project_data],
                key_field="raport_id",
                update_fields=["name", "description", "project_class"],
            )
            counts["projects"] += 1

            local_project = await self.wf_project_manager.search(raport_id=rp_id)
            if not local_project:
                log.warning(f"Project with raport_id={rp_id} not found after upsert, skipping")
                continue
            local_project_id = local_project[0].id

            # Traverse queues to reach construction objects
            queues = await _fetch_all(client, "list_project_queues", project_id=UUID(rp_id))
            for queue in queues:
                queue_id = UUID(str(queue["id"]))
                construction_objects = await _fetch_all(client, "list_queue_construction_objects", queue_id=queue_id)
                for co in construction_objects:
                    co_id = str(co["id"])
                    co_data = {
                        "raport_id": co_id,
                        "project_id": local_project_id,
                        "name": co.get("name", ""),
                        "description": co.get("description"),
                        "planned_end_date": co.get("planned_end_date"),
                    }
                    await self.wf_project_object_manager.bulk_upsert(
                        [co_data],
                        key_field="raport_id",
                        update_fields=["name", "description", "planned_end_date", "project_id"],
                    )
                    counts["construction_objects"] += 1

                    local_co = await self.wf_project_object_manager.search(raport_id=co_id)
                    if not local_co:
                        continue
                    local_co_id = local_co[0].id

                    housings = await _fetch_all(
                        client, "list_construction_object_housings", construction_object_id=UUID(co_id)
                    )
                    for h in housings:
                        h_id = str(h["id"])
                        housing_data = {
                            "raport_id": h_id,
                            "construction_object_id": local_co_id,
                            "name": h.get("name", ""),
                            "complex_name": h.get("complex_name") or h.get("project_name") or "",
                        }
                        await self.housing_manager.bulk_upsert(
                            [housing_data],
                            key_field="raport_id",
                            update_fields=["name", "complex_name", "construction_object_id"],
                        )
                        counts["housings"] += 1

                        local_h = await self.housing_manager.search(raport_id=h_id)
                        if not local_h:
                            continue
                        local_h_id = local_h[0].id

                        await self._sync_sections_floors(client, h_id, local_h_id, UUID(co_id), counts)

        return counts

    async def _sync_sections_floors(
        self,
        client: ReportClient,
        housing_raport_id: str,
        local_housing_id: UUID,
        co_uuid: UUID,
        counts: dict[str, int],
    ) -> None:
        sections = await _fetch_all(client, "list_housing_sections", housing_id=UUID(housing_raport_id))
        for s in sections:
            s_id = str(s["id"])
            section_data = {
                "raport_id": s_id,
                "housing_id": local_housing_id,
                "name": s.get("name", str(s.get("number", ""))),
                "section_number": s.get("number") or s.get("sort_order") or 0,
            }
            await self.section_manager.bulk_upsert(
                [section_data],
                key_field="raport_id",
                update_fields=["name", "section_number", "housing_id"],
            )
            counts["sections"] += 1

            local_s = await self.section_manager.search(raport_id=s_id)
            if not local_s:
                continue
            local_s_id = local_s[0].id

            floors = await _fetch_all(client, "list_section_floors", section_id=UUID(s_id))
            floor_rows = []
            for f in floors:
                floor_rows.append(
                    {
                        "raport_id": str(f["id"]),
                        "section_id": local_s_id,
                        "floor_number": f.get("number") or f.get("sort_order") or 0,
                        "name": f.get("name"),
                    }
                )
            if floor_rows:
                await self.floor_manager.bulk_upsert(
                    floor_rows,
                    key_field="raport_id",
                    update_fields=["floor_number", "name", "section_id"],
                )
                counts["floors"] += len(floor_rows)

    # ------------------------------------------------------------------
    # Group B — work catalog
    # ------------------------------------------------------------------

    async def sync_work_catalog(self) -> dict[str, int]:
        """Sync WorkGroup → WorkType from Raport."""
        client = ReportClient()
        counts: dict[str, int] = {"work_groups": 0, "work_types": 0}

        work_groups = await _fetch_all(client, "list_work_groups")
        for wg in work_groups:
            wg_id = str(wg["id"])
            wg_data = {
                "raport_id": wg_id,
                "name": wg.get("name", ""),
                "code": wg.get("code") or wg_id,
                "description": wg.get("description"),
            }
            await self.work_group_manager.bulk_upsert(
                [wg_data],
                key_field="raport_id",
                update_fields=["name", "code", "description"],
            )
            counts["work_groups"] += 1

            local_wg = await self.work_group_manager.search(raport_id=wg_id)
            if not local_wg:
                continue
            local_wg_id = local_wg[0].id

            work_types = await _fetch_all(client, "list_work_group_work_types", work_group_id=UUID(wg_id))
            wt_rows = []
            for wt in work_types:
                wt_rows.append(
                    {
                        "raport_id": str(wt["id"]),
                        "group_id": local_wg_id,
                        "name": wt.get("name", ""),
                        "code": wt.get("code") or str(wt["id"]),
                        "unit": wt.get("unit") or "шт",
                        "description": wt.get("description"),
                    }
                )
            if wt_rows:
                await self.work_type_manager.bulk_upsert(
                    wt_rows,
                    key_field="raport_id",
                    update_fields=["name", "code", "unit", "description", "group_id"],
                )
                counts["work_types"] += len(wt_rows)

        return counts

    # ------------------------------------------------------------------
    # Group C — contractors
    # ------------------------------------------------------------------

    async def sync_contractors(self) -> dict[str, int]:
        """Sync Contractor list from Raport."""
        client = ReportClient()
        contractors = await _fetch_all(client, "list_contractors")

        rows = []
        for c in contractors:
            rows.append(
                {
                    "raport_id": str(c["id"]),
                    "name": c.get("name", ""),
                    "short_name": c.get("short_name") or c.get("name", ""),
                    "inn": c.get("inn"),
                    "description": c.get("description"),
                }
            )

        if rows:
            await self.contractor_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "short_name", "inn", "description"],
            )

        return {"contractors": len(rows)}

    # ------------------------------------------------------------------
    # Payload-driven imports (xlsx dump → upsert; parents resolved by raport_id)
    # ------------------------------------------------------------------

    async def _resolve_parents(self, manager: BaseManager, raport_ids: Iterable[str]) -> dict[str, UUID]:
        """Build {raport_id: local_id} map for the given parent manager."""
        ids = {rid for rid in raport_ids if rid}
        if not ids:
            return {}
        rows = await manager.search(raport_id__in=list(ids))
        return {row.raport_id: row.id for row in rows if row.raport_id}

    async def import_projects(self, items: list[ImportProjectItem]) -> dict[str, int]:
        rows = [
            {
                "raport_id": i.raport_id,
                "name": i.name,
                "project_class": i.project_class,
                "description": i.description,
            }
            for i in items
        ]
        if rows:
            await self.wf_project_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "project_class", "description"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": 0}

    async def import_construction_objects(self, items: list[ImportConstructionObjectItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(self.wf_project_manager, (i.project_raport_id for i in items))
        rows = []
        missing = 0
        for i in items:
            project_id = parent_map.get(i.project_raport_id)
            if project_id is None:
                missing += 1
                continue
            rows.append(
                {
                    "raport_id": i.raport_id,
                    "project_id": project_id,
                    "name": i.name,
                    "description": i.description,
                    "planned_end_date": i.planned_end_date,
                }
            )
        if rows:
            await self.wf_project_object_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "description", "planned_end_date", "project_id"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": missing}

    async def import_housings(self, items: list[ImportHousingItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(
            self.wf_project_object_manager,
            (i.construction_object_raport_id for i in items if i.construction_object_raport_id),
        )
        rows = []
        missing = 0
        for i in items:
            co_id: UUID | None = None
            if i.construction_object_raport_id:
                co_id = parent_map.get(i.construction_object_raport_id)
                if co_id is None:
                    missing += 1
                    continue
            rows.append(
                {
                    "raport_id": i.raport_id,
                    "construction_object_id": co_id,
                    "name": i.name,
                    "complex_name": i.complex_name,
                    "description": i.description,
                }
            )
        if rows:
            await self.housing_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "complex_name", "construction_object_id", "description"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": missing}

    async def import_sections(self, items: list[ImportSectionItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(self.housing_manager, (i.housing_raport_id for i in items))
        rows = []
        missing = 0
        for i in items:
            housing_id = parent_map.get(i.housing_raport_id)
            if housing_id is None:
                missing += 1
                continue
            rows.append(
                {
                    "raport_id": i.raport_id,
                    "housing_id": housing_id,
                    "name": i.name,
                    "section_number": i.section_number,
                    "description": i.description,
                }
            )
        if rows:
            await self.section_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "section_number", "housing_id", "description"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": missing}

    async def import_floors(self, items: list[ImportFloorItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(self.section_manager, (i.section_raport_id for i in items))
        rows = []
        missing = 0
        for i in items:
            section_id = parent_map.get(i.section_raport_id)
            if section_id is None:
                missing += 1
                continue
            rows.append(
                {
                    "raport_id": i.raport_id,
                    "section_id": section_id,
                    "floor_number": i.floor_number,
                    "name": i.name,
                    "description": i.description,
                }
            )
        if rows:
            await self.floor_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["floor_number", "name", "section_id", "description"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": missing}

    async def import_work_groups(self, items: list[ImportWorkGroupItem]) -> dict[str, int]:
        rows = [
            {
                "raport_id": i.raport_id,
                "name": i.name,
                "code": i.code,
                "description": i.description,
            }
            for i in items
        ]
        if rows:
            await self.work_group_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "code", "description"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": 0}

    async def import_work_types(self, items: list[ImportWorkTypeItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(self.work_group_manager, (i.work_group_raport_id for i in items))
        rows = []
        missing = 0
        for i in items:
            group_id = parent_map.get(i.work_group_raport_id)
            if group_id is None:
                missing += 1
                continue
            rows.append(
                {
                    "raport_id": i.raport_id,
                    "group_id": group_id,
                    "name": i.name,
                    "code": i.code,
                    "unit": i.unit,
                    "description": i.description,
                }
            )
        if rows:
            await self.work_type_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "code", "unit", "description", "group_id"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": missing}

    async def import_contractors(self, items: list[ImportContractorItem]) -> dict[str, int]:
        rows = [
            {
                "raport_id": i.raport_id,
                "name": i.name,
                "short_name": (i.short_name or i.name)[:100],
                "inn": i.inn,
                "description": i.description,
            }
            for i in items
        ]
        if rows:
            await self.contractor_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "short_name", "inn", "description"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": 0}


async def get_sync_service(db: AsyncSession = Depends(get_session)) -> SyncService:
    return SyncService(db=db)
