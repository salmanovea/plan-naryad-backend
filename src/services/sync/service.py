"""
Raport sync service — pulls reference data from Raport and upserts it locally.

`SyncReportService` owns only the processing logic (transform, upsert, delete);
all communication with Raport (auth, requests, pagination) lives in `ReportApi`.

Three sync groups:
  A  objects — WfProject → WfProjectObject → Housing → Section → Floor
  B  work_catalog — WorkGroup → WorkType
  C  contractors — Contractor

Plus payload-driven `import_*` variants that accept Pydantic items instead
of calling the live Raport API. Used by offline xlsx dumps; same upsert
logic, same `raport_id` upsert key.
"""

from typing import Any, Awaitable, Callable, Iterable
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.sync.schemes import (
    ImportConstructionObjectItem,
    ImportContractItem,
    ImportContractorItem,
    ImportFloorItem,
    ImportHousingItem,
    ImportProjectItem,
    ImportSectionItem,
    ImportUserItem,
    ImportWorkGroupItem,
    ImportWorkTypeItem,
    SyncEntity,
    SyncImportRequest,
)
from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_session
from src.external.report.api import ReportApi
from src.models import managers
from src.models.dbo.tables.work import DependencyType
from src.models.managers.common import BaseManager
from src.services.common import BaseService

log = LoggerProvider().get_logger(__name__)


def _trim(value: Any, max_len: int | None) -> str | None:
    """Strip whitespace and clip to column length; returns None for empty/None input.

    Guards against Raport values that exceed local column limits (e.g. `inn`
    coming in as "1234567890/987654321" — longer than VARCHAR(20)). Pass
    max_len=None for unbounded Text columns (still strips + null-normalizes).
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if max_len is None else text[:max_len]


def _dedupe_by(rows: list[dict], key: str) -> list[dict]:
    """Drop duplicates by `key`, keeping the last occurrence.

    Guards ON CONFLICT DO UPDATE against Raport pagination that occasionally
    returns the same entity twice — Postgres refuses to touch the same row
    twice in one statement (CardinalityViolationError).
    """
    seen: dict[Any, dict] = {}
    for r in rows:
        seen[r[key]] = r
    return list(seen.values())


class SyncReportService(BaseService):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.report = ReportApi()
        self.wf_project_manager = managers.WfProjectManager(db)
        self.wf_project_object_manager = managers.WfProjectObjectManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.work_group_manager = managers.WorkGroupManager(db)
        self.work_type_manager = managers.WorkTypeManager(db)
        self.contractor_manager = managers.ContractorManager(db)
        self.contract_manager = managers.ContractManager(db)
        self.user_manager = managers.UserManager(db)
        self.contractor_assignment_manager = managers.ContractorAssignmentManager(db)
        self.tech_sequence_manager = managers.TechSequenceItemManager(db)

    # ------------------------------------------------------------------
    # Group A — objects hierarchy
    # ------------------------------------------------------------------

    async def sync_objects(self, project_raport_id: str | None = None) -> dict[str, int]:
        """Sync WfProject → WfProjectObject → Housing → Section → Floor from Raport."""
        counts: dict[str, int] = {
            "projects": 0,
            "construction_objects": 0,
            "housings": 0,
            "sections": 0,
            "floors": 0,
        }

        raport_projects = await self.report.list_all("list_projects")
        if project_raport_id:
            raport_projects = [p for p in raport_projects if str(p["id"]) == project_raport_id]

        for rp in raport_projects:
            rp_id = str(rp["id"])

            project_data = {
                "raport_id": rp_id,
                "name": _trim(rp.get("name"), 255) or "",
                "description": _trim(rp.get("description"), 1000),
                "project_class": _trim(rp.get("class"), 50) or "Комфорт",
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
            queues = await self.report.list_all("list_project_queues", project_id=UUID(rp_id))
            for queue in queues:
                queue_id = UUID(str(queue["id"]))
                construction_objects = await self.report.list_all("list_queue_construction_objects", queue_id=queue_id)
                for co in construction_objects:
                    co_id = str(co["id"])
                    co_data = {
                        "raport_id": co_id,
                        "project_id": local_project_id,
                        "name": _trim(co.get("name"), 255) or "",
                        "description": _trim(co.get("description"), 1000),
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

                    housings = await self.report.list_all(
                        "list_construction_object_housings", construction_object_id=UUID(co_id)
                    )
                    for h in housings:
                        h_id = str(h["id"])
                        housing_data = {
                            "raport_id": h_id,
                            "construction_object_id": local_co_id,
                            "name": _trim(h.get("name"), 255) or "",
                            "complex_name": _trim(h.get("complex_name") or h.get("project_name"), 255) or "",
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

                        await self._sync_sections_floors(h_id, local_h_id, UUID(co_id), counts)

        return counts

    async def _sync_sections_floors(
        self,
        housing_raport_id: str,
        local_housing_id: UUID,
        co_uuid: UUID,
        counts: dict[str, int],
    ) -> None:
        sections = await self.report.list_all("list_housing_sections", housing_id=UUID(housing_raport_id))
        for s in sections:
            s_id = str(s["id"])
            section_data = {
                "raport_id": s_id,
                "housing_id": local_housing_id,
                "name": _trim(s.get("name") or str(s.get("number", "")), 100) or "",
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

            floors = await self.report.list_all("list_section_floors", section_id=UUID(s_id))
            floor_rows = []
            for f in floors:
                floor_rows.append(
                    {
                        "raport_id": str(f["id"]),
                        "section_id": local_s_id,
                        "floor_number": f.get("number") or f.get("sort_order") or 0,
                        "name": _trim(f.get("name"), 100),
                    }
                )
            floor_rows = _dedupe_by(floor_rows, "raport_id")
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

    _WORK_TYPE_BATCH_SIZE = 4000

    @staticmethod
    def _default_unit(units: list[dict] | None) -> str:
        """Pick the default unit name from a Raport Work `units[]` array."""
        if not units:
            return "шт"
        for u in units:
            if u.get("is_default"):
                return _trim(u.get("name"), 20) or "шт"
        return _trim(units[0].get("name"), 20) or "шт"

    async def sync_work_catalog(self) -> dict[str, int]:
        """Sync the work catalog from Raport.

        Terminology (docs/sync-mapping.md §3): the local `work_groups` table
        («Виды работ») maps to Raport **WorkType**, and the local `work_types`
        table («Работы») maps to Raport **Work**. Raport WorkGroup/WorkSet are
        only traversed to reach work-types, never stored.

        Traversal: Raport work-groups → work-types (→ local WorkGroup) → works
        (→ local WorkType).
        """
        counts: dict[str, int] = {"work_groups": 0, "work_types": 0}

        raport_work_groups = await self.report.list_all("list_work_groups")
        for rwg in raport_work_groups:
            rwg_id = UUID(str(rwg["id"]))

            # Raport WorkTypes under this Raport WorkGroup → local WorkGroups
            raport_work_types = await self.report.list_all("list_work_group_work_types", work_group_id=rwg_id)
            for rwt in raport_work_types:
                rwt_id = str(rwt["id"])
                wg_data = {
                    "raport_id": rwt_id,
                    "name": _trim(rwt.get("name"), 255) or "",
                    "code": rwt_id[:50],
                }
                await self.work_group_manager.bulk_upsert(
                    [wg_data],
                    key_field="raport_id",
                    update_fields=["name", "code"],
                )
                counts["work_groups"] += 1

                local_wg = await self.work_group_manager.search(raport_id=rwt_id)
                if not local_wg:
                    continue
                local_wg_id = local_wg[0].id

                # Raport Works under this Raport WorkType → local WorkTypes
                works = await self.report.list_all("list_work_type_works", work_type_id=UUID(rwt_id))
                wt_rows = []
                for w in works:
                    w_id = str(w["id"])
                    wt_rows.append(
                        {
                            "raport_id": w_id,
                            "group_id": local_wg_id,
                            "name": _trim(w.get("name"), 255) or "",
                            "code": w_id[:100],
                            "unit": self._default_unit(w.get("units")),
                            "description": None,
                        }
                    )
                wt_rows = _dedupe_by(wt_rows, "raport_id")
                if wt_rows:
                    await self.work_type_manager.bulk_upsert(
                        wt_rows,
                        key_field="raport_id",
                        update_fields=["name", "code", "unit", "description", "group_id"],
                        batch_size=self._WORK_TYPE_BATCH_SIZE,
                    )
                    counts["work_types"] += len(wt_rows)

        return counts

    # ------------------------------------------------------------------
    # Group C — contractors
    # ------------------------------------------------------------------

    async def sync_contractors(self) -> dict[str, int]:
        """Sync Contractor list from Raport."""
        contractors = await self.report.list_all("list_contractors")

        rows = []
        for c in contractors:
            name = _trim(c.get("name"), 255) or ""
            rows.append(
                {
                    "raport_id": str(c["id"]),
                    "name": name,
                    "short_name": _trim(c.get("short_name"), 100) or name[:100],
                    "inn": _trim(c.get("inn"), 20),
                    "description": _trim(c.get("description"), 1000),
                }
            )

        rows = _dedupe_by(rows, "raport_id")
        if rows:
            await self.contractor_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "short_name", "inn", "description"],
            )

        return {"contractors": len(rows)}

    # ------------------------------------------------------------------
    # Group D — contracts
    # ------------------------------------------------------------------

    async def sync_contracts(self) -> dict[str, int]:
        """Sync the contract list from Raport (flat `GET /api/v1/contracts`).

        Each contract's Raport `contractor_id` is resolved to a local contractor;
        the contract is still stored (with a null contractor) if that contractor
        has not been synced yet. The contract identifier field is `subject`.
        """
        contracts = await self.report.list_all("list_contracts")

        contractor_ids = {str(c["contractor_id"]) for c in contracts if c.get("contractor_id")}
        contractor_map = await self._resolve_parents(self.contractor_manager, contractor_ids)

        rows = []
        for c in contracts:
            raport_contractor_id = str(c["contractor_id"]) if c.get("contractor_id") else None
            rows.append(
                {
                    "raport_id": str(c["id"]),
                    "contractor_id": contractor_map.get(raport_contractor_id) if raport_contractor_id else None,
                    "name": _trim(c.get("name"), 500),
                    "subject": _trim(c.get("subject"), None),
                    "is_warranty_letter": bool(c.get("is_warranty_letter")),
                }
            )

        rows = _dedupe_by(rows, "raport_id")
        if rows:
            await self.contract_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["contractor_id", "name", "subject", "is_warranty_letter"],
            )

        return {"contracts": len(rows)}

    # ------------------------------------------------------------------
    # Group E — users
    # ------------------------------------------------------------------

    @staticmethod
    def _user_row(u: dict) -> dict:
        return {
            "raport_id": str(u["id"]),
            "last_name": _trim(u.get("last_name"), 255),
            "first_name": _trim(u.get("first_name"), 255),
            "middle_name": _trim(u.get("middle_name"), 255),
            "shown_name": _trim(u.get("shown_name"), 500),
            "email": _trim(u.get("email"), 255),
            "is_external": bool(u.get("is_external")),
            "groups": u.get("groups") or [],
            "project_ids": [str(p["id"]) for p in (u.get("projects") or []) if p.get("id")],
            "contractor_ids": [str(c["id"]) for c in (u.get("contractors") or []) if c.get("id")],
        }

    # 11 columns per row; keep rows × columns under asyncpg's 32767 bind-param cap.
    _USER_BATCH_SIZE = 2000
    _USER_UPDATE_FIELDS = [
        "last_name",
        "first_name",
        "middle_name",
        "shown_name",
        "email",
        "is_external",
        "groups",
        "project_ids",
        "contractor_ids",
    ]

    async def sync_users(self) -> dict[str, int]:
        """Sync the user directory from Raport (`GET /api/v1/users`)."""
        users = await self.report.list_all("list_users")
        rows = _dedupe_by([self._user_row(u) for u in users], "raport_id")
        if rows:
            await self.user_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=self._USER_UPDATE_FIELDS,
                batch_size=self._USER_BATCH_SIZE,
            )
        return {"users": len(rows)}

    # ------------------------------------------------------------------
    # Group F — contractor assignments (aggregated from Raport)
    # ------------------------------------------------------------------

    # 7 columns per row (incl. generated id); keep rows × columns under
    # asyncpg's 32767 bind-param cap.
    _ASSIGNMENT_BATCH_SIZE = 4000

    async def sync_assignments(self, housing_raport_id: str | None = None) -> dict[str, int]:
        """Sync contractor assignments from the aggregated Raport endpoint.

        Terminology (docs/sync-mapping.md §3+§4.2): the aggregate groups by
        Raport WorkGroup and lists Raport WorkTypes; each Raport WorkType is a
        *local* WorkGroup. So one aggregate row is exploded into one local
        `ContractorAssignment` per work-type, keyed by the composite
        `(contractor_id, housing_id, section_id, work_group_id)`. `work_type_ids`
        is left empty (the contractor covers the whole work-group).

        Reconciliation is snapshot-based and scoped: pass `housing_raport_id` to
        sync one housing (its `source="raport"` rows absent from the response are
        deleted); omit it for a full sync. Rows with `source="manual"` are never
        touched.
        """
        params: dict[str, Any] = {}
        local_scope_housing_id: UUID | None = None
        if housing_raport_id:
            params["housing_id"] = housing_raport_id
            scope_local = await self.housing_manager.search(raport_id=housing_raport_id)
            if not scope_local:
                return {"assignments": 0, "deleted": 0, "skipped": 0}
            local_scope_housing_id = scope_local[0].id

        rows_src = await self.report.list_all("list_assignments_aggregated", **params)

        contractor_map = await self._resolve_parents(
            self.contractor_manager, (r["contractor"]["id"] for r in rows_src if r.get("contractor"))
        )
        housing_map = await self._resolve_parents(
            self.housing_manager, (r["housing"]["id"] for r in rows_src if r.get("housing"))
        )
        section_map = await self._resolve_parents(
            self.section_manager, (r["section"]["id"] for r in rows_src if r.get("section"))
        )
        work_group_map = await self._resolve_parents(
            self.work_group_manager,
            (wt["id"] for r in rows_src for wt in (r.get("work_types") or []) if wt.get("id")),
        )

        desired: dict[tuple, dict] = {}
        skipped = 0
        for r in rows_src:
            contractor_id = contractor_map.get(str(r["contractor"]["id"])) if r.get("contractor") else None
            housing_id = housing_map.get(str(r["housing"]["id"])) if r.get("housing") else None
            section_id = section_map.get(str(r["section"]["id"])) if r.get("section") else None
            if not contractor_id or not housing_id:
                skipped += 1
                continue
            for wt in r.get("work_types") or []:
                work_group_id = work_group_map.get(str(wt["id"]))
                if not work_group_id:
                    skipped += 1
                    continue
                key = (contractor_id, housing_id, section_id, work_group_id)
                desired[key] = {
                    "contractor_id": contractor_id,
                    "housing_id": housing_id,
                    "section_id": section_id,
                    "work_group_id": work_group_id,
                    "work_type_ids": [],
                    "source": "raport",
                }

        if desired:
            await self.contractor_assignment_manager.bulk_upsert(
                list(desired.values()),
                key_field=["contractor_id", "housing_id", "section_id", "work_group_id"],
                update_fields=["work_type_ids", "source"],
                batch_size=self._ASSIGNMENT_BATCH_SIZE,
            )

        deleted = await self._delete_stale_assignments(set(desired), local_scope_housing_id)
        return {"assignments": len(desired), "deleted": deleted, "skipped": skipped}

    async def _delete_stale_assignments(self, fresh_keys: set[tuple], scope_housing_id: UUID | None) -> int:
        """Delete `source="raport"` assignments (within scope) absent from the snapshot."""
        filters: dict[str, Any] = {"source": "raport"}
        if scope_housing_id is not None:
            filters["housing_id"] = scope_housing_id
        existing = await self.contractor_assignment_manager.search(**filters)
        stale_ids = [
            a.id for a in existing if (a.contractor_id, a.housing_id, a.section_id, a.work_group_id) not in fresh_keys
        ]
        if stale_ids:
            await self.contractor_assignment_manager.bulk_delete_by_batch(stale_ids)
            await self.db.commit()
        return len(stale_ids)

    # ------------------------------------------------------------------
    # Group G — technological sequence (from a plan's links[])
    # ------------------------------------------------------------------

    # 11 columns per row (incl. generated id); stay under asyncpg's 32767 cap.
    _TECH_SEQUENCE_BATCH_SIZE = 2000

    async def _load_plan_structure(self, housing_raport_id: str) -> tuple[dict, str | None]:
        """Return (plan, source_kind) for a housing: its calendar plan if one
        exists, otherwise the default plan-template. `plan` has `data` (tasks)
        and `links` (predecessor edges)."""
        check = await self.report.check_calendar_plan(housing_id=housing_raport_id)
        if check.get("is_exists") and check.get("data"):
            cp = await self.report.get_calendar_plan(str(check["data"][0]["id"]))
            return (cp.get("plan") or {}, "calendar")

        templates = await self.report.list_plan_templates(is_default="true", per_page=1)
        tdata = templates.get("data") or []
        if not tdata:
            return ({}, None)
        tpl = await self.report.get_plan_template_data(str(tdata[0]["id"]))
        return (tpl.get("plan") or {}, "template")

    async def sync_tech_sequence(self, housing_raport_id: str) -> dict[str, int]:
        """Sync the technological sequence for one housing from Raport.

        Source: the housing's calendar plan if it exists, else the default
        plan-template (docs/sync-mapping.md §4.1). Plan tasks map to local
        WorkTypes via `task.work.id` (Raport Work); `plan.links[]` (source→target
        task edges) become `depends_on` at the work-type level. Volumes are not
        in Raport — they are set to 0 on insert and left untouched on re-sync so
        manual edits survive. Keyed by `(housing_id, work_type_id)`; `source="raport"`
        rows absent from the new snapshot are deleted.
        """
        local = await self.housing_manager.search(raport_id=housing_raport_id)
        if not local:
            return {"tech_sequence": 0, "deleted": 0, "skipped": 0}
        housing_id = local[0].id

        plan, _ = await self._load_plan_structure(housing_raport_id)
        tasks = plan.get("data") or []
        links = plan.get("links") or []

        # task.work.id (Raport Work) → local WorkType
        work_ids = {str(t["work"]["id"]) for t in tasks if t.get("work") and t["work"].get("id")}
        wt_map = await self._resolve_parents(self.work_type_manager, work_ids)
        task_wt: dict[str, UUID] = {}
        for t in tasks:
            w = t.get("work") or {}
            wid = str(w["id"]) if w.get("id") else None
            if wid and wid in wt_map:
                task_wt[str(t["id"])] = wt_map[wid]

        # predecessors per task → predecessor work-type ids
        preds: dict[str, set[str]] = {}
        for link in links:
            src, tgt = str(link.get("source")), str(link.get("target"))
            if src in task_wt and tgt in task_wt:
                preds.setdefault(tgt, set()).add(str(task_wt[src]))

        rows_by_wt: dict[UUID, dict] = {}
        skipped = 0
        for t in tasks:
            tid = str(t["id"])
            wt = task_wt.get(tid)
            if not wt:
                skipped += 1
                continue
            order = int(t.get("line_number") or 0)
            duration = int(t.get("duration") or 0)
            deps = {d for d in preds.get(tid, set()) if d != str(wt)}
            row = rows_by_wt.get(wt)
            if row:
                row["order"] = min(row["order"], order)
                row["depends_on"] = sorted(set(row["depends_on"]) | deps)
                row["estimated_days"] = max(row["estimated_days"], duration)
            else:
                rows_by_wt[wt] = {
                    "housing_id": housing_id,
                    "work_type_id": wt,
                    "order": order,
                    "depends_on": sorted(deps),
                    "dependency_type": DependencyType.FINISH_TO_START.value,
                    "lag_days": int(t.get("lag") or 0),
                    "estimated_days": duration,
                    "daily_norm_volume": 0,
                    "total_volume": 0,
                    "source": "raport",
                }

        if rows_by_wt:
            await self.tech_sequence_manager.bulk_upsert(
                list(rows_by_wt.values()),
                key_field=["housing_id", "work_type_id"],
                # volumes are intentionally excluded so manual edits survive a re-sync
                update_fields=["order", "depends_on", "dependency_type", "lag_days", "estimated_days", "source"],
                batch_size=self._TECH_SEQUENCE_BATCH_SIZE,
            )

        deleted = await self._delete_stale_tech_sequence(housing_id, set(rows_by_wt))
        return {"tech_sequence": len(rows_by_wt), "deleted": deleted, "skipped": skipped}

    async def _delete_stale_tech_sequence(self, housing_id: UUID, fresh_work_type_ids: set[UUID]) -> int:
        """Delete `source="raport"` sequence rows for a housing absent from the snapshot."""
        existing = await self.tech_sequence_manager.search(housing_id=housing_id, source="raport")
        stale_ids = [r.id for r in existing if r.work_type_id not in fresh_work_type_ids]
        if stale_ids:
            await self.tech_sequence_manager.bulk_delete_by_batch(stale_ids)
            await self.db.commit()
        return len(stale_ids)

    # ------------------------------------------------------------------
    # Unified dispatchers (one entry point for /sync and /sync/import)
    # ------------------------------------------------------------------

    # Entities whose live sync is covered by a single hierarchical traversal.
    _OBJECTS_ENTITIES = frozenset(
        {
            SyncEntity.PROJECTS,
            SyncEntity.CONSTRUCTION_OBJECTS,
            SyncEntity.HOUSINGS,
            SyncEntity.SECTIONS,
            SyncEntity.FLOORS,
        }
    )
    _CATALOG_ENTITIES = frozenset({SyncEntity.WORK_KINDS, SyncEntity.WORKS})

    async def sync(self, entities: list[SyncEntity] | None = None) -> dict[str, dict]:
        """Live-sync the selected entities from Raport (all of them if None/empty).

        Granular entities are grouped into the hierarchical fetch operations:
        any of projects/construction_objects/housings/sections/floors triggers a
        single `sync_objects` traversal; work_kinds/works trigger a single
        `sync_work_catalog`.
        """
        selected = set(entities) if entities else set(SyncEntity)
        result: dict[str, dict] = {}

        if SyncEntity.USERS in selected:
            result["users"] = await self.sync_users()
        if SyncEntity.CONTRACTORS in selected:
            result["contractors"] = await self.sync_contractors()
        if SyncEntity.CONTRACTS in selected:
            result["contracts"] = await self.sync_contracts()
        if selected & self._OBJECTS_ENTITIES:
            result["objects"] = await self.sync_objects()
        if selected & self._CATALOG_ENTITIES:
            result["work_catalog"] = await self.sync_work_catalog()
        if SyncEntity.ASSIGNMENTS in selected:
            result["assignments"] = await self.sync_assignments()
        if SyncEntity.TECH_SEQUENCE in selected:
            result["tech_sequence"] = await self._sync_tech_sequence_all()

        return result

    async def _sync_tech_sequence_all(self) -> dict[str, int]:
        """Sync the technological sequence for every local housing that has a
        Raport id. Heavy (per-housing plan fetch) — prefer the scoped
        `sync_tech_sequence(housing_raport_id)` for routine use."""
        housings = await self.housing_manager.search(raport_id__isnotnull=True)
        totals = {"tech_sequence": 0, "deleted": 0, "skipped": 0, "housings": 0}
        for h in housings:
            if not h.raport_id:
                continue
            res = await self.sync_tech_sequence(h.raport_id)
            totals["tech_sequence"] += res["tech_sequence"]
            totals["deleted"] += res["deleted"]
            totals["skipped"] += res["skipped"]
            totals["housings"] += 1
        return totals

    async def import_entities(self, payload: SyncImportRequest) -> dict[str, dict]:
        """Offline-import the selected entities from the request payload.

        `payload.entities` selects which entities to process; if it is None/empty,
        every entity that has a payload list provided is processed. Entities are
        run parent-before-child so `*_raport_id` references resolve.
        """
        selected = set(payload.entities) if payload.entities else None
        # (entity, payload list, handler) in parent → child order
        plan: list[tuple[SyncEntity, list | None, Callable[[Any], Awaitable[dict[str, int]]]]] = [
            (SyncEntity.USERS, payload.users, self.import_users),
            (SyncEntity.CONTRACTORS, payload.contractors, self.import_contractors),
            (SyncEntity.CONTRACTS, payload.contracts, self.import_contracts),
            (SyncEntity.PROJECTS, payload.projects, self.import_projects),
            (SyncEntity.CONSTRUCTION_OBJECTS, payload.construction_objects, self.import_construction_objects),
            (SyncEntity.HOUSINGS, payload.housings, self.import_housings),
            (SyncEntity.SECTIONS, payload.sections, self.import_sections),
            (SyncEntity.FLOORS, payload.floors, self.import_floors),
            (SyncEntity.WORK_KINDS, payload.work_kinds, self.import_work_groups),
            (SyncEntity.WORKS, payload.works, self.import_work_types),
        ]
        result: dict[str, dict] = {}
        for entity, items, handler in plan:
            if selected is not None and entity not in selected:
                continue
            if items is None:
                continue
            result[entity.value] = await handler(items)
        return result

    # ------------------------------------------------------------------
    # Payload-driven imports (xlsx dump → upsert; parents resolved by raport_id)
    # ------------------------------------------------------------------

    _RESOLVE_PARENTS_CHUNK = 30000

    async def _resolve_parents(self, manager: BaseManager, raport_ids: Iterable[str]) -> dict[str, UUID]:
        """Build {raport_id: local_id} map for the given parent manager."""
        ids = [rid for rid in {rid for rid in raport_ids if rid}]
        if not ids:
            return {}
        result: dict[str, UUID] = {}
        for start in range(0, len(ids), self._RESOLVE_PARENTS_CHUNK):
            chunk = ids[start : start + self._RESOLVE_PARENTS_CHUNK]
            rows = await manager.search(raport_id__in=chunk)
            for row in rows:
                if row.raport_id:
                    result[row.raport_id] = row.id
        return result

    async def import_projects(self, items: list[ImportProjectItem]) -> dict[str, int]:
        rows = [
            {
                "raport_id": i.raport_id,
                "name": _trim(i.name, 255) or "",
                "project_class": _trim(i.project_class, 50) or "Комфорт",
                "description": _trim(i.description, 1000),
            }
            for i in items
        ]
        rows = _dedupe_by(rows, "raport_id")
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
                    "name": _trim(i.name, 255) or "",
                    "description": _trim(i.description, 1000),
                    "planned_end_date": i.planned_end_date,
                }
            )
        rows = _dedupe_by(rows, "raport_id")
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
                    "name": _trim(i.name, 255) or "",
                    "complex_name": _trim(i.complex_name, 255) or "",
                    "description": _trim(i.description, 1000),
                }
            )
        rows = _dedupe_by(rows, "raport_id")
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
                    "name": _trim(i.name, 100) or "",
                    "section_number": i.section_number,
                    "description": _trim(i.description, 500),
                }
            )
        rows = _dedupe_by(rows, "raport_id")
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
                    "name": _trim(i.name, 100),
                    "description": _trim(i.description, 500),
                }
            )
        rows = _dedupe_by(rows, "raport_id")
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
                "name": _trim(i.name, 255) or "",
                "code": _trim(i.code, 50) or i.raport_id[:50],
                "description": _trim(i.description, 1000),
            }
            for i in items
        ]
        rows = _dedupe_by(rows, "raport_id")
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
                    "name": _trim(i.name, 255) or "",
                    "code": _trim(i.code, 100) or i.raport_id[:100],
                    "unit": _trim(i.unit, 20) or "шт",
                    "description": _trim(i.description, 1000),
                }
            )
        rows = _dedupe_by(rows, "raport_id")
        if rows:
            await self.work_type_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "code", "unit", "description", "group_id"],
                batch_size=self._WORK_TYPE_BATCH_SIZE,
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": missing}

    async def import_contractors(self, items: list[ImportContractorItem]) -> dict[str, int]:
        rows = []
        for i in items:
            name = _trim(i.name, 255) or ""
            rows.append(
                {
                    "raport_id": i.raport_id,
                    "name": name,
                    "short_name": _trim(i.short_name, 100) or name[:100],
                    "inn": _trim(i.inn, 20),
                    "description": _trim(i.description, 1000),
                }
            )
        rows = _dedupe_by(rows, "raport_id")
        if rows:
            await self.contractor_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "short_name", "inn", "description"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": 0}

    async def import_contracts(self, items: list[ImportContractItem]) -> dict[str, int]:
        contractor_map = await self._resolve_parents(
            self.contractor_manager, (i.contractor_raport_id for i in items if i.contractor_raport_id)
        )
        rows = []
        for i in items:
            rows.append(
                {
                    "raport_id": i.raport_id,
                    "contractor_id": contractor_map.get(i.contractor_raport_id) if i.contractor_raport_id else None,
                    "name": _trim(i.name, 500),
                    "subject": _trim(i.subject, None),
                    "is_warranty_letter": i.is_warranty_letter,
                }
            )
        rows = _dedupe_by(rows, "raport_id")
        if rows:
            await self.contract_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["contractor_id", "name", "subject", "is_warranty_letter"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": 0}

    async def import_users(self, items: list[ImportUserItem]) -> dict[str, int]:
        rows = [
            {
                "raport_id": i.raport_id,
                "last_name": _trim(i.last_name, 255),
                "first_name": _trim(i.first_name, 255),
                "middle_name": _trim(i.middle_name, 255),
                "shown_name": _trim(i.shown_name, 500),
                "email": _trim(i.email, 255),
                "is_external": i.is_external,
                "groups": i.groups,
                "project_ids": i.project_ids,
                "contractor_ids": i.contractor_ids,
            }
            for i in items
        ]
        rows = _dedupe_by(rows, "raport_id")
        if rows:
            await self.user_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=self._USER_UPDATE_FIELDS,
                batch_size=self._USER_BATCH_SIZE,
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": 0}


async def get_sync_report_service(db: AsyncSession = Depends(get_session)) -> SyncReportService:
    return SyncReportService(db=db)
