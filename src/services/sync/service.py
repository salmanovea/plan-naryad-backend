"""
Raport sync service — pulls reference data from Raport and upserts it locally.

`SyncReportService` owns only the processing logic (transform, upsert, delete);
all communication with Raport (auth, requests, pagination) lives in `ReportApi`.

Three sync groups:
  A  objects — Project → Queue → ConstructionObject → Housing → Section → Floor
  B  work_catalog — WorkSet → WorkGroup → WorkType → Work
  C  contractors — Contractor

Plus payload-driven `import_*` variants that accept Pydantic items instead
of calling the live Raport API. Used by offline xlsx dumps; same upsert
logic, same `raport_id` upsert key.
"""

from datetime import date, datetime, timedelta
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
    ImportWorkItem,
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
from src.utils.business_time import business_today, business_tz
from src.services.common import BaseService, end_transaction
from src.services.contractor_works import ContractorWorksService, HousingAssignments

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


def _as_date(value: Any) -> date | None:
    """Raport sends an ISO datetime; the column is a plain date and asyncpg wants a date.

    Raport normalizes datetimes to UTC on output, so the calendar date must be taken in
    *local* time (TZ=Europe/Moscow in the containers): a fact entered 28.08 00:30 MSK
    arrives as `…-27T21:30:00Z` and would otherwise land on the 27th (DEV-6858, item 11).
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(business_tz())
    return parsed.date()


def _nested_id(payload: Any, *keys: str) -> str | None:
    """Pull a nested id out of a Raport row, tolerating nulls at any level."""
    node = payload
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return str(node) if node else None


class SyncReportService(BaseService):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.report = ReportApi()
        self.project_manager = managers.ProjectManager(db)
        self.queue_manager = managers.QueueManager(db)
        self.construction_object_manager = managers.ConstructionObjectManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.work_set_manager = managers.WorkSetManager(db)
        self.work_group_manager = managers.WorkGroupManager(db)
        self.work_type_manager = managers.WorkTypeManager(db)
        self.work_manager = managers.WorkManager(db)
        self.contractor_manager = managers.ContractorManager(db)
        self.contract_manager = managers.ContractManager(db)
        self.user_manager = managers.UserManager(db)
        self.tech_sequence_manager = managers.TechSequenceItemManager(db)
        self.work_fact_manager = managers.WorkFactManager(db)

    # ------------------------------------------------------------------
    # Group A — objects hierarchy
    # ------------------------------------------------------------------

    async def sync_objects(self, project_raport_id: str | None = None) -> dict[str, int]:
        """Sync Project → ConstructionObject → Housing → Section → Floor from Raport."""
        counts: dict[str, int] = {
            "projects": 0,
            "queues": 0,
            "construction_objects": 0,
            "housings": 0,
            "sections": 0,
            "floors": 0,
        }

        raport_projects = await self.report.list_all("list_projects")
        if project_raport_id:
            raport_projects = [p for p in raport_projects if str(p["id"]) == project_raport_id]
        log.info("sync_objects: traversing %d Raport project(s)", len(raport_projects))

        for proj_idx, rp in enumerate(raport_projects, start=1):
            rp_id = str(rp["id"])
            log.info(
                "sync_objects: [%d/%d] project '%s' (raport_id=%s)",
                proj_idx,
                len(raport_projects),
                _trim(rp.get("name"), 255) or "",
                rp_id,
            )

            project_data = {
                "raport_id": rp_id,
                "name": _trim(rp.get("name"), 255) or "",
                "description": _trim(rp.get("description"), 1000),
                "project_class": _trim(rp.get("class"), 50) or "Комфорт",
            }
            await self.project_manager.bulk_upsert(
                [project_data],
                key_field="raport_id",
                update_fields=["name", "description", "project_class"],
            )
            counts["projects"] += 1

            local_project = await self.project_manager.search(raport_id=rp_id)
            if not local_project:
                log.warning(f"Project with raport_id={rp_id} not found after upsert, skipping")
                continue
            local_project_id = local_project[0].id

            # Queues are stored now (they are a required filter level), not just traversed.
            queues = await self.report.list_all("list_project_queues", project_id=UUID(rp_id))
            for queue in queues:
                queue_id = UUID(str(queue["id"]))
                queue_raport_id = str(queue["id"])
                await self.queue_manager.bulk_upsert(
                    [
                        {
                            "raport_id": queue_raport_id,
                            "project_id": local_project_id,
                            "name": _trim(queue.get("name"), 255) or "",
                        }
                    ],
                    key_field="raport_id",
                    update_fields=["name", "project_id"],
                )
                counts["queues"] += 1
                local_queue = await self.queue_manager.search(raport_id=queue_raport_id)
                local_queue_id = local_queue[0].id if local_queue else None

                construction_objects = await self.report.list_all("list_queue_construction_objects", queue_id=queue_id)
                for co in construction_objects:
                    co_id = str(co["id"])
                    co_data = {
                        "raport_id": co_id,
                        "project_id": local_project_id,
                        "queue_id": local_queue_id,
                        "name": _trim(co.get("name"), 255) or "",
                        "description": _trim(co.get("description"), 1000),
                        "planned_end_date": co.get("planned_end_date"),
                    }
                    await self.construction_object_manager.bulk_upsert(
                        [co_data],
                        key_field="raport_id",
                        update_fields=["name", "description", "planned_end_date", "project_id", "queue_id"],
                    )
                    counts["construction_objects"] += 1

                    local_co = await self.construction_object_manager.search(raport_id=co_id)
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

        log.info("sync_objects: done — %s", counts)
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
                        "floor_number": f.get("sort_order") or 0,
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

    _WORK_BATCH_SIZE = 4000

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
        """Sync the whole work catalogue from Raport in a single request.

        `GET /api/v1/works/structure` returns the complete tree flat, one row per node,
        with `level` numbering it: 0 = work_set, 1 = work_group, 2 = work_type, 3 = work
        (the leaf, the only level carrying units). `parent_id` links a node to the level
        above. That replaces the old nested traversal, which issued one request per
        Raport work-group and stored only two of the four levels.

        Names now line up with Raport one-to-one (decision Р6b), so no level shifting
        happens here any more.
        """
        counts: dict[str, int] = {"work_sets": 0, "work_groups": 0, "work_types": 0, "works": 0}

        response = await self.report.get_works_structure()
        nodes = response.get("data") or []
        log.info("sync_work_catalog: fetched %d catalogue nodes", len(nodes))

        by_level: dict[int, list[dict]] = {0: [], 1: [], 2: [], 3: []}
        for node in nodes:
            level = node.get("level")
            if level in by_level:
                by_level[level].append(node)

        # Level 0 — work sets. No parent.
        set_rows = _dedupe_by(
            [
                {
                    "raport_id": str(n["id"]),
                    "name": _trim(n.get("title"), 255) or "",
                    "code": str(n["id"])[:100],
                }
                for n in by_level[0]
            ],
            "raport_id",
        )
        if set_rows:
            await self.work_set_manager.bulk_upsert(set_rows, key_field="code", update_fields=["name", "raport_id"])
        counts["work_sets"] = len(set_rows)
        set_map = await self._resolve_parents(self.work_set_manager, (r["raport_id"] for r in set_rows))

        # Levels 1..3 — each resolves its parent through the level above.
        group_rows = _dedupe_by(
            [
                {
                    "raport_id": str(n["id"]),
                    "work_set_id": set_map.get(str(n.get("parent_id"))),
                    "name": _trim(n.get("title"), 255) or "",
                    "code": str(n["id"])[:100],
                }
                for n in by_level[1]
            ],
            "raport_id",
        )
        if group_rows:
            await self.work_group_manager.bulk_upsert(
                group_rows, key_field="code", update_fields=["name", "work_set_id", "raport_id"]
            )
        counts["work_groups"] = len(group_rows)
        group_map = await self._resolve_parents(self.work_group_manager, (r["raport_id"] for r in group_rows))

        type_rows = _dedupe_by(
            [
                {
                    "raport_id": str(n["id"]),
                    "work_group_id": group_map.get(str(n.get("parent_id"))),
                    "name": _trim(n.get("title"), 255) or "",
                    "code": str(n["id"])[:50],
                }
                for n in by_level[2]
            ],
            "raport_id",
        )
        if type_rows:
            await self.work_type_manager.bulk_upsert(
                type_rows, key_field="code", update_fields=["name", "work_group_id", "raport_id"]
            )
        counts["work_types"] = len(type_rows)
        type_map = await self._resolve_parents(self.work_type_manager, (r["raport_id"] for r in type_rows))

        work_rows = []
        for n in by_level[3]:
            parent = type_map.get(str(n.get("parent_id")))
            if parent is None:
                continue
            work_rows.append(
                {
                    "raport_id": str(n["id"]),
                    "work_type_id": parent,
                    "name": _trim(n.get("title"), 255) or "",
                    "code": str(n["id"])[:100],
                    "unit": self._default_unit(n.get("units")),
                    "description": None,
                }
            )
        work_rows = _dedupe_by(work_rows, "raport_id")
        if work_rows:
            await self.work_manager.bulk_upsert(
                work_rows,
                key_field="code",
                update_fields=["name", "unit", "description", "work_type_id", "raport_id"],
                batch_size=self._WORK_BATCH_SIZE,
            )
        counts["works"] = len(work_rows)
        log.info("sync_work_catalog: upserted %s", counts)

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
    # Group G — work facts (mirrored from Raport, never authored locally)
    # ------------------------------------------------------------------

    _FACT_BATCH_SIZE = 2000
    _FACT_PER_PAGE = 200

    async def sync_work_facts(
        self,
        housing_raport_id: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, int]:
        """Pull one housing's facts from Raport for a date window.

        Facts are entered in Raport only (spec: creating them here is out of scope), so this
        is a one-way mirror keyed by `raport_id` (Raport's `work_fact.id`).

        Raport leaves `contractor` empty on virtually every fact — 0 of 56 365 on the
        reference housing — so the contractor is resolved from the cell's assignment
        (`/contractor-works`), which covers 99.5% of cells. Facts on a cell shared by several
        contractors are stored without one rather than attributed by guesswork.

        Without a window the default is yesterday and today, which is what the nightly run
        needs; a full re-pull is done by passing an explicit range.
        """
        local = await self.housing_manager.search(raport_id=housing_raport_id)
        if not local:
            return {"work_facts": 0, "skipped": 0, "without_contractor": 0}
        housing_id = local[0].id

        if date_from is None and date_to is None:
            date_to = business_today()
            date_from = date_to - timedelta(days=1)

        await end_transaction(self.db)
        rows_src = await self._fetch_work_facts(housing_raport_id, date_from, date_to)
        if not rows_src:
            return {"work_facts": 0, "skipped": 0, "without_contractor": 0}

        section_map = await self._reverse_raport_map(self.section_manager, housing_id=housing_id)
        floor_map = await self._floor_raport_map(housing_id)
        work_map = await self._resolve_parents(self.work_manager, (_nested_id(r, "work", "id") or "" for r in rows_src))

        assignments = await ContractorWorksService(self.db, report=self.report).get_housing_assignments(housing_id)

        rows: list[dict] = []
        skipped = 0
        without_contractor = 0
        for src in rows_src:
            section_id = section_map.get(_nested_id(src, "section", "id") or "")
            floor_id = floor_map.get(_nested_id(src, "floor", "id") or "")
            work_id = work_map.get(_nested_id(src, "work", "id") or "")
            if not section_id or not floor_id or not work_id:
                skipped += 1
                continue

            contractor_id = await self._resolve_fact_contractor(src, section_id, floor_id, work_id, assignments)
            if contractor_id is None:
                without_contractor += 1

            work_date = _as_date(src.get("work_date"))
            rows.append(
                {
                    "raport_id": str(src["id"]),
                    "work_date": work_date,
                    "housing_id": housing_id,
                    "section_id": section_id,
                    "floor_id": floor_id,
                    "work_id": work_id,
                    "contractor_id": contractor_id,
                    "volume": src.get("volume") or 0,
                    "percent": src.get("percent"),
                    "unit": _trim((src.get("unit") or {}).get("name"), 20),
                    "work_cell_id": src.get("work_cell_id"),
                    "work_cell_contractor_id": src.get("work_cell_contractor_id"),
                    "submitted_by": _trim((src.get("user") or {}).get("shown_name"), 255),
                    "source": "raport",
                }
            )

        rows = [r for r in _dedupe_by(rows, "raport_id") if r["work_date"]]
        if rows:
            await self.work_fact_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=[
                    "work_date",
                    "housing_id",
                    "section_id",
                    "floor_id",
                    "work_id",
                    "contractor_id",
                    "volume",
                    "percent",
                    "unit",
                    "work_cell_id",
                    "work_cell_contractor_id",
                    "submitted_by",
                    "source",
                ],
                batch_size=self._FACT_BATCH_SIZE,
            )

        result = {"work_facts": len(rows), "skipped": skipped, "without_contractor": without_contractor}
        log.info("sync_work_facts: housing %s (%s..%s) — %s", housing_raport_id, date_from, date_to, result)
        return result

    async def _fetch_work_facts(
        self,
        housing_raport_id: str,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict]:
        """Walk every page of `/work-facts` for a housing and window."""
        params: dict[str, Any] = {"housing_id": housing_raport_id}
        if date_from:
            params["work_date__gte"] = str(date_from)
        if date_to:
            params["work_date__lte"] = str(date_to)

        rows: list[dict] = []
        page = 1
        while True:
            try:
                response = await self.report.list_work_facts(page=page, per_page=self._FACT_PER_PAGE, **params)
            except Exception as err:
                log.error("sync_work_facts: read failed on page %d: %s", page, err)
                break
            items = (response or {}).get("data") or []
            rows.extend(items)
            next_page = ((response or {}).get("pagination") or {}).get("next_page")
            if not next_page or not items:
                break
            page = next_page
        return rows

    @staticmethod
    async def _resolve_fact_contractor(
        src: dict,
        section_id: UUID,
        floor_id: UUID,
        work_id: UUID,
        assignments: "HousingAssignments",
    ) -> UUID | None:
        """Raport's own contractor first, the cell's sole assignee second, else nothing."""
        raport_contractor = _nested_id(src, "contractor", "id")
        if raport_contractor:
            # Raport named the contractor itself; trust it when it resolves locally.
            for candidate in assignments.contractors_for(section_id, floor_id, work_id):
                return candidate
        return assignments.single_contractor_for(section_id, floor_id, work_id)

    async def _reverse_raport_map(self, manager: BaseManager, **filters: Any) -> dict[str, UUID]:
        """{raport_id: local id} for a filtered table."""
        rows = await manager.search(**filters)
        return {row.raport_id: row.id for row in rows if getattr(row, "raport_id", None)}

    async def _floor_raport_map(self, housing_id: UUID) -> dict[str, UUID]:
        """{floor raport_id: local id} for every floor of a housing."""
        sections = await self.section_manager.search(housing_id=housing_id)
        section_ids = [s.id for s in sections]
        if not section_ids:
            return {}
        floors = await self.floor_manager.search(section_id__in=section_ids)
        return {f.raport_id: f.id for f in floors if f.raport_id}

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
    _TECH_SEQUENCE_BATCH_SIZE = 2000

    async def _load_plan_structure(
        self,
        housing_raport_id: str,
        section_raport_id: str | None = None,
    ) -> tuple[dict, str | None]:
        """Return (plan, source_kind) for a housing or one of its sections.

        Raport builds calendar plans at both scopes, so the lookup is scoped too: with
        `section_raport_id` it asks for that section's plan and gives up if there is none
        (the housing-wide plan already covers the section). Without it, it falls back to
        the default plan-template.

        `plan` carries `data` (tasks) and `links` (predecessor edges).
        """
        params = {"housing_id": housing_raport_id}
        if section_raport_id:
            params["section_id"] = section_raport_id
        check = await self.report.check_calendar_plan(**params)
        if check.get("is_exists") and check.get("data"):
            cp = await self.report.get_calendar_plan(str(check["data"][0]["id"]))
            return (cp.get("plan") or {}, "calendar")

        if section_raport_id:
            return ({}, None)

        templates = await self.report.list_plan_templates(is_default="true", per_page=1)
        tdata = templates.get("data") or []
        if not tdata:
            return ({}, None)
        tpl = await self.report.get_plan_template_data(str(tdata[0]["id"]))
        return (tpl.get("plan") or {}, "template")

    async def sync_tech_sequence(self, housing_raport_id: str) -> dict[str, int]:
        """Sync the technological sequences of one housing from Raport.

        Two scopes are pulled: the housing-wide calendar plan (falling back to the default
        plan-template), and a plan per section for those sections that have their own — in
        the dev database 11 of 19 plans are section-scoped. Section rows carry `section_id`
        and override the housing-wide rows for that section during generation.

        The sequence is a graph: `plan.links[]` edges become `depends_on` (finish-to-start)
        and `depends_on_ss` (start-to-start) depending on the link type. Volumes are absent
        in Raport — set to 0 on insert and left alone on re-sync so manual edits survive.
        Keyed by `(housing_id, section_id, work_id)`; `source="raport"` rows absent from the
        fresh snapshot are deleted within their own scope.
        """
        local = await self.housing_manager.search(raport_id=housing_raport_id)
        if not local:
            return {"tech_sequence": 0, "deleted": 0, "skipped": 0}
        housing_id = local[0].id

        totals = {"tech_sequence": 0, "deleted": 0, "skipped": 0}

        plan, _ = await self._load_plan_structure(housing_raport_id)
        await self._store_sequence_scope(plan, housing_id, None, totals)

        for section in await self.section_manager.search(housing_id=housing_id):
            if not section.raport_id:
                continue
            section_plan, kind = await self._load_plan_structure(housing_raport_id, section.raport_id)
            if kind is None:
                continue
            await self._store_sequence_scope(section_plan, housing_id, section.id, totals)

        return totals

    async def _store_sequence_scope(
        self,
        plan: dict,
        housing_id: UUID,
        section_id: UUID | None,
        totals: dict[str, int],
    ) -> None:
        """Upsert one scope's sequence rows and drop the stale ones in that same scope."""
        rows, skipped = await self._build_sequence_rows(plan, housing_id, section_id)
        totals["skipped"] += skipped
        if rows:
            await self.tech_sequence_manager.bulk_upsert(
                rows,
                key_field=["housing_id", "section_id", "work_id"],
                # volumes are intentionally excluded so manual edits survive a re-sync
                update_fields=[
                    "order",
                    "depends_on",
                    "depends_on_ss",
                    "lag_days",
                    "planning_type",
                    "floor_sorting_direction",
                    "lag_between_floors",
                    "estimated_days",
                    "source",
                ],
                batch_size=self._TECH_SEQUENCE_BATCH_SIZE,
            )
        totals["tech_sequence"] += len(rows)
        totals["deleted"] += await self._delete_stale_tech_sequence(
            housing_id, section_id, {r["work_id"] for r in rows}
        )

    async def _build_sequence_rows(
        self,
        plan: dict,
        housing_id: UUID,
        section_id: UUID | None,
    ) -> tuple[list[dict], int]:
        """Turn a Raport plan into sequence rows for one scope.

        The same work can appear as several plan tasks (for instance once per floor); rows
        are merged per work, taking the earliest order, the longest duration and the union
        of predecessors.
        """
        tasks = plan.get("data") or []
        links = plan.get("links") or []

        work_raport_ids = {str(t["work"]["id"]) for t in tasks if t.get("work") and t["work"].get("id")}
        work_map = await self._resolve_parents(self.work_manager, work_raport_ids)

        task_work: dict[str, UUID] = {}
        for t in tasks:
            work = t.get("work") or {}
            raport_id = str(work["id"]) if work.get("id") else None
            if raport_id and raport_id in work_map:
                task_work[str(t["id"])] = work_map[raport_id]

        # Predecessors, split by link type. Raport sends dhtmlx codes: "1" is start-to-start,
        # everything else is treated as finish-to-start.
        preds_fs: dict[str, set[str]] = {}
        preds_ss: dict[str, set[str]] = {}
        for link in links:
            source, target = str(link.get("source")), str(link.get("target"))
            if source not in task_work or target not in task_work:
                continue
            bucket = (
                preds_ss if DependencyType.from_dhtmlx(link.get("type")) is DependencyType.START_TO_START else preds_fs
            )
            bucket.setdefault(target, set()).add(str(task_work[source]))

        rows_by_work: dict[UUID, dict] = {}
        skipped = 0
        for t in tasks:
            task_id = str(t["id"])
            work_id = task_work.get(task_id)
            if not work_id:
                skipped += 1
                continue

            order = int(t.get("line_number") or 0)
            duration = int(t.get("duration") or 0)
            own = str(work_id)
            deps_fs = {d for d in preds_fs.get(task_id, set()) if d != own}
            deps_ss = {d for d in preds_ss.get(task_id, set()) if d != own}

            row = rows_by_work.get(work_id)
            if row:
                row["order"] = min(row["order"], order)
                row["depends_on"] = sorted(set(row["depends_on"]) | deps_fs)
                row["depends_on_ss"] = sorted(set(row["depends_on_ss"]) | deps_ss)
                row["estimated_days"] = max(row["estimated_days"], duration)
                continue

            rows_by_work[work_id] = {
                "housing_id": housing_id,
                "section_id": section_id,
                "work_id": work_id,
                "order": order,
                "depends_on": sorted(deps_fs),
                "depends_on_ss": sorted(deps_ss),
                "lag_days": int(t.get("lag") or 0),
                # How the work travels through floors (Р6a) — the generator needs these.
                "planning_type": _trim(t.get("planning_type"), 20),
                "floor_sorting_direction": _trim(t.get("floor_sorting_direction"), 4),
                "lag_between_floors": t.get("lag_between_floors"),
                "estimated_days": duration,
                "daily_norm_volume": 0,
                "total_volume": 0,
                "source": "raport",
            }

        return list(rows_by_work.values()), skipped

    async def _delete_stale_tech_sequence(
        self,
        housing_id: UUID,
        section_id: UUID | None,
        fresh_work_ids: set[UUID],
    ) -> int:
        """Delete `source="raport"` rows of one scope that the fresh snapshot dropped."""
        filters: dict = {"housing_id": housing_id, "source": "raport"}
        filters["section_id"] = section_id if section_id else None
        existing = await self.tech_sequence_manager.search(**filters)
        stale_ids: list[int | UUID] = [
            r.id for r in existing if r.work_id not in fresh_work_ids and r.section_id == section_id
        ]
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

        steps: list[tuple[str, Callable[[], Awaitable[dict[str, int]]]]] = []
        if SyncEntity.USERS in selected:
            steps.append(("users", self.sync_users))
        if SyncEntity.CONTRACTORS in selected:
            steps.append(("contractors", self.sync_contractors))
        if SyncEntity.CONTRACTS in selected:
            steps.append(("contracts", self.sync_contracts))
        if selected & self._OBJECTS_ENTITIES:
            steps.append(("objects", self.sync_objects))
        if selected & self._CATALOG_ENTITIES:
            steps.append(("work_catalog", self.sync_work_catalog))
        if SyncEntity.TECH_SEQUENCE in selected:
            steps.append(("tech_sequence", self._sync_tech_sequence_all))

        total = len(steps)
        log.info("sync: starting — %d group(s) to sync: %s", total, ", ".join(key for key, _ in steps))
        for idx, (key, handler) in enumerate(steps, start=1):
            log.info("sync: [%d/%d] syncing '%s'...", idx, total, key)
            result[key] = await handler()
            log.info("sync: [%d/%d] '%s' done — %s", idx, total, key, result[key])
        log.info("sync: finished all %d group(s)", total)

        return result

    async def _sync_tech_sequence_all(self) -> dict[str, int]:
        """Sync the technological sequence for every local housing that has a
        Raport id. Heavy (per-housing plan fetch) — prefer the scoped
        `sync_tech_sequence(housing_raport_id)` for routine use."""
        housings = await self.housing_manager.search(raport_id__isnotnull=True)
        candidates = [h for h in housings if h.raport_id]
        log.info("tech_sequence: syncing sequence for %d housing(s) with a Raport id", len(candidates))
        totals = {"tech_sequence": 0, "deleted": 0, "skipped": 0, "housings": 0}
        for idx, h in enumerate(candidates, start=1):
            raport_id = h.raport_id
            if not raport_id:
                continue
            res = await self.sync_tech_sequence(raport_id)
            totals["tech_sequence"] += res["tech_sequence"]
            totals["deleted"] += res["deleted"]
            totals["skipped"] += res["skipped"]
            totals["housings"] += 1
            if idx % 10 == 0 or idx == len(candidates):
                log.info(
                    "tech_sequence: processed %d/%d housings (%d sequence rows, %d deleted so far)",
                    idx,
                    len(candidates),
                    totals["tech_sequence"],
                    totals["deleted"],
                )
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
            (SyncEntity.WORK_KINDS, payload.work_kinds, self.import_work_types),
            (SyncEntity.WORKS, payload.works, self.import_works),
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
            await self.project_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "project_class", "description"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": 0}

    async def import_construction_objects(self, items: list[ImportConstructionObjectItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(self.project_manager, (i.project_raport_id for i in items))
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
            await self.construction_object_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "description", "planned_end_date", "project_id"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": missing}

    async def import_housings(self, items: list[ImportHousingItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(
            self.construction_object_manager,
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

    async def import_work_types(self, items: list[ImportWorkTypeItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(
            self.work_group_manager, (i.work_group_raport_id for i in items if i.work_group_raport_id)
        )
        rows = [
            {
                "raport_id": i.raport_id,
                "work_group_id": parent_map.get(i.work_group_raport_id) if i.work_group_raport_id else None,
                "name": _trim(i.name, 255) or "",
                "code": _trim(i.code, 50) or i.raport_id[:50],
                "description": _trim(i.description, 1000),
            }
            for i in items
        ]
        rows = _dedupe_by(rows, "raport_id")
        if rows:
            await self.work_type_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "code", "description", "work_group_id"],
            )
        return {"received": len(items), "upserted": len(rows), "missing_parents": 0}

    async def import_works(self, items: list[ImportWorkItem]) -> dict[str, int]:
        parent_map = await self._resolve_parents(self.work_type_manager, (i.work_type_raport_id for i in items))
        rows = []
        missing = 0
        for i in items:
            work_type_id = parent_map.get(i.work_type_raport_id)
            if work_type_id is None:
                missing += 1
                continue
            rows.append(
                {
                    "raport_id": i.raport_id,
                    "work_type_id": work_type_id,
                    "name": _trim(i.name, 255) or "",
                    "code": _trim(i.code, 100) or i.raport_id[:100],
                    "unit": _trim(i.unit, 20) or "шт",
                    "description": _trim(i.description, 1000),
                }
            )
        rows = _dedupe_by(rows, "raport_id")
        if rows:
            await self.work_manager.bulk_upsert(
                rows,
                key_field="raport_id",
                update_fields=["name", "code", "unit", "description", "work_type_id"],
                batch_size=self._WORK_BATCH_SIZE,
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
