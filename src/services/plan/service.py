"""Plan-naryad autogeneration.

The generator reads the technological sequence as the **graph** it is (a finished work can
unlock several successors; a work can need several predecessors finished) and reads progress
from the Raport chessboard at `work_cell_contractor` grain, where each contractor on a cell
has their own percent. Volumes play no part any more — nobody sets a daily norm.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemes import PaginationParams
from src.api.v1.plan.schemes import PlanItemSchema
from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_session
from src.config.settings import app_config
from src.models import managers
from src.models.dbo.tables.plan import PlanItem, PlanSource, PlanStatus
from src.models.dbo.tables.settings import ActionType
from src.models.dbo.tables.work import FloorSortingDirection
from src.services.common import SYSTEM_ACTOR, BaseService, floor_label
from src.services.contractor_works import ContractorWorksService
from src.services.report_cells import CellKey, HousingSlice, ReportCellsService

log = LoggerProvider().get_logger(__name__)

# Fallback for calls with no authenticated user: scheduler jobs and AUTH_ENABLED=false.
UNKNOWN_ACTOR = SYSTEM_ACTOR


@dataclass
class TechNode:
    """One work in a scope's technological graph."""

    work_id: UUID
    order: int
    depends_on: set[UUID] = field(default_factory=set)
    depends_on_ss: set[UUID] = field(default_factory=set)
    floor_sorting_direction: str = FloorSortingDirection.ASC.value


def _as_uuids(values: Optional[List[str]]) -> set[UUID]:
    """Predecessors are stored as text; malformed entries are dropped rather than fatal."""
    result: set[UUID] = set()
    for value in values or []:
        try:
            result.add(UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            log.warning("plan: skipping malformed predecessor id %r", value)
    return result


def default_target_date(now: Optional[datetime] = None) -> date:
    """Today before the transfer cutoff, tomorrow after it (decision Р3).

    The 03:00 scheduled run lands on today; a run started during the day or the evening
    targets tomorrow, because today's positions have already gone to the contractors.
    """
    moment = now or datetime.now()
    if moment.hour < app_config.plan_transfer_cutoff_hour:
        return moment.date()
    return moment.date() + timedelta(days=1)


class AutogenerationService(BaseService):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.plan_item_manager = managers.PlanItemManager(db)
        self.work_fact_manager = managers.WorkFactManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.construction_object_manager = managers.ConstructionObjectManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.work_manager = managers.WorkManager(db)
        self.work_type_manager = managers.WorkTypeManager(db)
        self.work_group_manager = managers.WorkGroupManager(db)
        self.work_set_manager = managers.WorkSetManager(db)
        self.tech_sequence_manager = managers.TechSequenceItemManager(db)
        self.contractor_manager = managers.ContractorManager(db)
        self.floor_limit_manager = managers.ContractorFloorLimitManager(db)
        self.action_log_manager = managers.ActionLogManager(db)
        self.report_cells = ReportCellsService(db)
        self.contractor_works = ContractorWorksService(db)

    @staticmethod
    def _enrich_plan_item(item: PlanItem) -> PlanItemSchema:
        """Map a plan item (with relations loaded) to a schema with readable labels."""
        schema = PlanItemSchema.model_validate(item)
        floor = item.floor
        if floor:
            schema.floor_number = floor.floor_number
            schema.floor_name = floor_label(floor)
        schema.section_name = item.section.name if item.section else None
        schema.contractor_name = item.contractor.name if item.contractor else None

        work = item.work
        if work:
            schema.work_name = work.name
            work_type = work.work_type
            schema.work_type_name = work_type.name if work_type else None
            group = work_type.work_group if work_type else None
            schema.work_group_name = group.name if group else None
            work_set = group.work_set if group else None
            schema.work_set_name = work_set.name if work_set else None
        return schema

    async def list_plan_items(
        self,
        pagination: PaginationParams,
        order_by: List[str],
        **filters,
    ) -> Tuple[List[PlanItemSchema], int]:
        """List plan items with denormalized section/floor/work/contractor names."""
        query = self.plan_item_manager.get_enriched_query()
        items = await self.plan_item_manager.search(query=query, order_by=order_by, pagination=pagination, **filters)
        total = await self.plan_item_manager.count(**filters)
        return [self._enrich_plan_item(i) for i in items], total

    async def get_plan_items(self, order_by: Optional[List[str]] = None, **filters) -> List[PlanItemSchema]:
        """Fetch plan items (no pagination) with denormalized labels."""
        query = self.plan_item_manager.get_enriched_query()
        items = await self.plan_item_manager.search(query=query, order_by=order_by, **filters)
        return [self._enrich_plan_item(i) for i in items]

    async def get_plan_item(self, plan_item_id: UUID) -> Optional[PlanItemSchema]:
        """Fetch a single plan item with denormalized labels."""
        item = await self.plan_item_manager.get_enriched_by_id(plan_item_id)
        return self._enrich_plan_item(item) if item else None

    async def has_plan_for(
        self,
        housing_id: UUID,
        target_date: date,
        section_id: Optional[UUID] = None,
    ) -> bool:
        """Whether the day already holds positions — the re-run confirmation gate."""
        scope: dict = {"housing_id": housing_id, "date": target_date}
        if section_id:
            scope["section_id"] = section_id
        return bool(await self.plan_item_manager.search(**scope))

    async def housings_of_projects(self, project_ids: list[UUID]) -> list[UUID]:
        """Housings under the given projects — `project_id` is a filter, not a column.

        The chain is project → construction_object → housing, so the narrowing is two hops.
        """
        objects = await self.construction_object_manager.search(project_id__in=list(project_ids))
        if not objects:
            return []
        housings = await self.housing_manager.search(construction_object_id__in=[o.id for o in objects])
        return [h.id for h in housings]

    # ── Public feed for the Raport chessboard ─────────────────────────────────

    async def daily_assignment(
        self,
        housing_raport_id: str,
        target_date: date,
        section_raport_id: Optional[str] = None,
    ) -> list[dict]:
        """Positions handed to the contractors, addressed in Raport's own ids.

        Raport calls this to decide which cells stay active when «Задание на день» is switched
        on, so the input is Raport ids (it does not know ours) and so is the output. Only
        `transferred` positions qualify: a draft has not been given to anyone yet, and the
        spec ties the toggle to «Передано подрядчику».

        An empty list is a valid answer — it means the toggle should be inactive.
        """
        housings = await self.housing_manager.search(raport_id=housing_raport_id)
        if not housings:
            return []

        scope: dict = {
            "housing_id": housings[0].id,
            "date": target_date,
            "status": PlanStatus.TRANSFERRED.value,
        }
        if section_raport_id:
            sections = await self.section_manager.search(housing_id=housings[0].id, raport_id=section_raport_id)
            if not sections:
                return []
            scope["section_id"] = sections[0].id

        items = await self.plan_item_manager.search(**scope)
        if not items:
            return []

        # Translate local references back to Raport ids in bulk.
        section_map = {s.id: s for s in await self.section_manager.get_by_ids([i.section_id for i in items])}
        floors = {f.id: f for f in await self.floor_manager.get_by_ids([i.floor_id for i in items])}
        works = {w.id: w for w in await self.work_manager.get_by_ids([i.work_id for i in items])}
        contractors = {c.id: c for c in await self.contractor_manager.get_by_ids([i.contractor_id for i in items])}

        return [
            {
                "work_cell_contractor_id": item.work_cell_contractor_id,
                "work_cell_id": item.work_cell_id,
                "section_id": getattr(section_map.get(item.section_id), "raport_id", None),
                "floor_id": getattr(floors.get(item.floor_id), "raport_id", None),
                "work_id": getattr(works.get(item.work_id), "raport_id", None),
                "contractor_id": getattr(contractors.get(item.contractor_id), "raport_id", None),
                "plan_item_id": item.id,
                "status": item.status,
            }
            for item in items
        ]

    # ── Lookups for the manual-add dialog ─────────────────────────────────────

    async def _narrow_to_floor(self, works: list, section_id: UUID, floor_id: UUID) -> list:
        """Keep only the works that Raport's chessboard has on that floor.

        Returns the input untouched when narrowing is impossible — the section or the floor is
        not mirrored from Raport, or Raport is unreachable. Losing the dialog entirely is worse
        than showing more works than necessary.
        """
        section = await self.section_manager.get_by_id(section_id)
        floor = await self.floor_manager.get_by_id(floor_id)
        if not section or not section.raport_id or not floor or not floor.raport_id:
            log.info("available_works: section %s or floor %s has no raport_id, not narrowing", section_id, floor_id)
            return works

        allowed = await self.report_cells.works_on_floor(section.raport_id, floor.raport_id)
        if allowed is None:
            return works

        narrowed = [work for work in works if work.raport_id and work.raport_id in allowed]
        log.info(
            "available_works: floor %s narrowed the list from %s works to %s",
            floor_id,
            len(works),
            len(narrowed),
        )
        return narrowed

    async def available_works(self, housing_id: UUID, section_id: UUID, floor_id: UUID) -> list[dict]:
        """Works offerable on a floor, as the «Этап → Комплекс → Вид → Работа» tree.

        Two filters, in this order: the calendar plan (a section with its own plan is limited to
        it, the rest fall back to the housing-wide one), then the floor itself — only works that
        have a cell there, as Raport's chessboard sees it.

        If Raport cannot say which works belong to the floor, the wider list is offered rather
        than an empty one: an outage must not look like «nothing can be done here».
        """
        housing_nodes, section_nodes = await self._load_tech_nodes(housing_id)
        nodes = section_nodes.get(section_id) or housing_nodes
        if not nodes:
            return []

        works = await self.work_manager.get_by_ids(list(nodes))
        works = await self._narrow_to_floor(works, section_id, floor_id)
        if not works:
            return []
        type_ids = {w.work_type_id for w in works if w.work_type_id}
        types = {t.id: t for t in await self.work_type_manager.get_by_ids(list(type_ids))}
        group_ids = {t.work_group_id for t in types.values() if t.work_group_id}
        groups = {g.id: g for g in await self.work_group_manager.get_by_ids(list(group_ids))}
        set_ids = {g.work_set_id for g in groups.values() if g.work_set_id}
        sets = {s.id: s for s in await self.work_set_manager.get_by_ids(list(set_ids))}

        tree: list[dict] = []
        for work in sorted(works, key=lambda w: w.name):
            work_type = types.get(work.work_type_id)
            group = groups.get(work_type.work_group_id) if work_type and work_type.work_group_id else None
            work_set = sets.get(group.work_set_id) if group and group.work_set_id else None
            tree.append(
                {
                    "work_set": {"id": work_set.id, "name": work_set.name} if work_set else None,
                    "work_group": {"id": group.id, "name": group.name} if group else None,
                    "work_type": {"id": work_type.id, "name": work_type.name} if work_type else None,
                    "work": {"id": work.id, "name": work.name},
                }
            )
        return tree

    async def available_contractors(self, work_id: UUID, floor_id: UUID) -> list[dict]:
        """Contractors assigned to a work on a floor, per the spec's dropdown rule."""
        contractor_ids = await self.contractor_works.get_contractors_for_cell(work_id=work_id, floor_id=floor_id)
        if not contractor_ids:
            return []
        contractors = await self.contractor_manager.get_by_ids(list(contractor_ids))
        return [{"id": c.id, "name": c.name} for c in sorted(contractors, key=lambda c: c.name)]

    # ── Operations on positions ───────────────────────────────────────────────

    async def add_manual_item(
        self,
        housing_id: UUID,
        section_id: UUID,
        floor_id: UUID,
        work_id: UUID,
        contractor_id: UUID,
        target_date: date,
        actor: str = UNKNOWN_ACTOR,
    ) -> Tuple[Optional[PlanItem], Optional[str]]:
        """Add a position by hand. Returns (item, error).

        The spec lets the user step outside the technological sequence here, so no readiness
        check — but the contractor must actually be assigned to this work on this floor,
        otherwise the position would be undeliverable.

        Percent and Raport cell ids are filled from the chessboard when the cell is known;
        a work the user picked outside the plan may have no cell yet, which is not an error.
        """
        section = await self.section_manager.get_by_id(section_id)
        floor = await self.floor_manager.get_by_id(floor_id)
        work = await self.work_manager.get_by_id(work_id)
        if not section or section.housing_id != housing_id:
            return None, "Секция не найдена в этом корпусе."
        if not floor or floor.section_id != section_id:
            return None, "Этаж не найден в этой секции."
        if not work:
            return None, "Работа не найдена."

        allowed = await self.contractor_works.get_contractors_for_cell(work_id=work_id, floor_id=floor_id)
        if contractor_id not in allowed:
            return None, (
                f"Не назначен подрядчик для работы {work.name} секция {section.name} "
                f"этаж {floor_label(floor)}. Добавьте назначение в системе Рапорт."
            )

        slice_ = await self.report_cells.get_housing_slice(housing_id, work_ids=[work_id])
        state = slice_.cells.get(CellKey(section_id, floor_id, work_id, contractor_id))

        item = await self.plan_item_manager.create(
            {
                "date": target_date,
                "housing_id": housing_id,
                "section_id": section_id,
                "floor_id": floor_id,
                "work_id": work_id,
                "contractor_id": contractor_id,
                "source_percent": state.percent if state else None,
                "work_cell_contractor_id": state.work_cell_contractor_id if state else None,
                "work_cell_id": state.work_cell_id if state else None,
                "source": PlanSource.MANUAL,
                "status": PlanStatus.DRAFT,
            }
        )
        await self.log_action(ActionType.PLAN_ITEM_CREATE, item.id, actor, {"date": str(target_date)})
        return item, None

    async def confirm_item(self, plan_item_id: UUID, actor: str = UNKNOWN_ACTOR) -> Optional[PlanItem]:
        """`draft` → `confirmed`. The spec has no way back — a wrong position is deleted."""
        item = await self.plan_item_manager.update_by_id(
            plan_item_id,
            {
                "rs_confirmed": True,
                "rs_confirmed_at": datetime.now(),
                "rs_confirmed_by": actor,
                "status": PlanStatus.CONFIRMED.value,
            },
        )
        if item:
            await self.log_action(ActionType.PLAN_ITEM_CONFIRM, plan_item_id, actor)
        return item

    async def delete_item(self, plan_item_id: UUID, actor: str = UNKNOWN_ACTOR) -> bool:
        """Physical delete — editing a position means deleting and adding a correct one."""
        item = await self.plan_item_manager.get_by_id(plan_item_id)
        if not item:
            return False
        await self.plan_item_manager.delete_by_id(plan_item_id)
        await self.log_action(ActionType.PLAN_ITEM_DELETE, plan_item_id, actor, {"date": str(item.date)})
        return True

    async def confirm_items(self, plan_item_ids: list[UUID], actor: str = UNKNOWN_ACTOR) -> dict:
        """Confirm several positions at once.

        A day on one housing runs to ~136 positions, so confirming them one by one is not a
        workable flow. Ids that do not exist are reported rather than silently ignored.
        """
        items = await self.plan_item_manager.get_by_ids(list(set(plan_item_ids)))
        found = {item.id for item in items}
        if items:
            confirmed_at = datetime.now()
            await self.plan_item_manager.bulk_update_by_batch(
                [
                    {
                        "id": item.id,
                        "rs_confirmed": True,
                        "rs_confirmed_at": confirmed_at,
                        "rs_confirmed_by": actor,
                        "status": PlanStatus.CONFIRMED.value,
                    }
                    for item in items
                ]
            )
            for item in items:
                await self.log_action(ActionType.PLAN_ITEM_CONFIRM, item.id, actor)
        return {"confirmed": len(found), "not_found": [str(i) for i in set(plan_item_ids) - found]}

    async def delete_items(self, plan_item_ids: list[UUID], actor: str = UNKNOWN_ACTOR) -> dict:
        """Delete several positions at once — the group counterpart of `delete_item`."""
        items = await self.plan_item_manager.get_by_ids(list(set(plan_item_ids)))
        found = {item.id for item in items}
        if items:
            for item in items:
                await self.log_action(ActionType.PLAN_ITEM_DELETE, item.id, actor, {"date": str(item.date)})
            await self.plan_item_manager.bulk_delete(list(found))
            await self.db.commit()
        return {"deleted": len(found), "not_found": [str(i) for i in set(plan_item_ids) - found]}

    async def transfer_day(
        self,
        target_date: date,
        housing_id: Optional[UUID] = None,
        section_id: Optional[UUID] = None,
    ) -> dict:
        """Hand the day over to the contractors.

        Per the spec, once the cutoff passes every position that was not deleted goes to the
        contractor whether or not it was confirmed — so both `draft` and `confirmed` move.
        Idempotent: positions already transferred are left alone.
        """
        scope: dict = {"date": target_date, "status__in": [PlanStatus.DRAFT.value, PlanStatus.CONFIRMED.value]}
        if housing_id:
            scope["housing_id"] = housing_id
        if section_id:
            scope["section_id"] = section_id

        items = await self.plan_item_manager.search(**scope)
        if not items:
            return {"transferred": 0}
        await self.plan_item_manager.bulk_update_by_batch(
            [{"id": item.id, "status": PlanStatus.TRANSFERRED.value} for item in items]
        )
        log.info("plan: transferred %d positions for %s", len(items), target_date)
        return {"transferred": len(items)}

    async def log_action(
        self,
        action: ActionType,
        entity_id: Optional[UUID] = None,
        actor: str = UNKNOWN_ACTOR,
        payload: Optional[dict] = None,
    ) -> None:
        """Journal one of the four actions the spec requires to be traceable.

        `actor` is the Keycloak id of the user behind the request (see
        `src/services/common/actor.py` — an id, not a name, deliberately), or «system» for
        scheduler jobs and for local runs with AUTH_ENABLED=false.
        """
        await self.action_log_manager.create(
            {
                "action": action.value,
                "entity_type": "plan_item",
                "entity_id": entity_id,
                "actor": actor,
                "payload": payload,
            }
        )

    # ── Readiness over the technological graph ────────────────────────────────

    def _ready_works(
        self,
        nodes: dict[UUID, "TechNode"],
        section_id: UUID,
        floor_id: UUID,
        slice_: HousingSlice,
    ) -> list[UUID]:
        """Works whose predecessors are all satisfied on this particular cell.

        The sequence is a graph, so «the next work» is not one work but a frontier: every
        node whose finish-to-start predecessors are finished and whose start-to-start
        predecessors have at least started. A node already finished here is not returned.

        Ordering follows `order` (the plan's line number) so the caller walks the frontier
        in the sequence author's intended order.
        """
        ready: list[tuple[int, UUID]] = []
        for work_id, node in nodes.items():
            states = slice_.states_on(section_id, floor_id, work_id)
            if not states:
                continue
            if all(state.is_done for state in states):
                continue
            if all(self._cell_done(section_id, floor_id, dep, slice_) for dep in node.depends_on):
                if all(self._cell_started(section_id, floor_id, dep, slice_) for dep in node.depends_on_ss):
                    ready.append((node.order, work_id))
        return [work_id for _, work_id in sorted(ready)]

    @staticmethod
    def _cell_done(section_id: UUID, floor_id: UUID, work_id: UUID, slice_: HousingSlice) -> bool:
        """A work is finished on a cell when every contractor on it is finished.

        Absent from the slice means Raport has no such cell — treated as not finished, so a
        missing predecessor never unlocks a successor by accident.
        """
        states = slice_.states_on(section_id, floor_id, work_id)
        return bool(states) and all(state.is_done for state in states)

    @staticmethod
    def _cell_started(section_id: UUID, floor_id: UUID, work_id: UUID, slice_: HousingSlice) -> bool:
        """A work has started on a cell when any contractor shows progress."""
        return any(state.percent > 0 for state in slice_.states_on(section_id, floor_id, work_id))

    # ── Sequence scope: a section's own plan wins over the housing-wide one ────

    async def _load_tech_nodes(
        self, housing_id: UUID
    ) -> tuple[dict[UUID, "TechNode"], dict[UUID, dict[UUID, "TechNode"]]]:
        """Return (housing-wide nodes, {section_id: nodes}).

        Raport builds calendar plans per housing and per section; a section that has its
        own plan is generated from it alone, the rest fall back to the housing-wide one.
        """
        rows = await self.tech_sequence_manager.search(housing_id=housing_id, order_by=["order"])
        housing_nodes: dict[UUID, TechNode] = {}
        section_nodes: dict[UUID, dict[UUID, TechNode]] = {}
        for row in rows:
            node = TechNode(
                work_id=row.work_id,
                order=row.order,
                depends_on=_as_uuids(row.depends_on),
                depends_on_ss=_as_uuids(row.depends_on_ss),
                floor_sorting_direction=row.floor_sorting_direction or FloorSortingDirection.ASC.value,
            )
            if row.section_id:
                section_nodes.setdefault(row.section_id, {})[row.work_id] = node
            else:
                housing_nodes[row.work_id] = node
        return housing_nodes, section_nodes

    # ── Floor limits ──────────────────────────────────────────────────────────

    async def _floor_limits(self) -> dict[tuple[Optional[UUID], UUID], int]:
        """`(contractor_id | None, work_id) → floors_limit` from contractor_floor_limits."""
        rows = await self.floor_limit_manager.search()
        return {(row.contractor_id, row.work_id): row.floors_limit for row in rows}

    @staticmethod
    def _limit_for(
        limits: dict[tuple[Optional[UUID], UUID], int],
        contractor_id: UUID,
        work_id: UUID,
    ) -> int:
        """Cascade from Р8: exact match, then the work-wide row, then the default."""
        if (contractor_id, work_id) in limits:
            return limits[(contractor_id, work_id)]
        if (None, work_id) in limits:
            return limits[(None, work_id)]
        return app_config.default_floor_limit

    # ── Generation ────────────────────────────────────────────────────────────

    async def generate_daily_plan(
        self,
        housing_id: UUID,
        target_date: date,
        section_id: Optional[UUID] = None,
        force: bool = False,
        actor: str = UNKNOWN_ACTOR,
    ) -> Tuple[List, List[str]]:
        """Build the day plan for a housing. Returns (items, reasons).

        Steps follow the spec: check that a calendar plan exists, read the chessboard, walk
        the readiness frontier of the technological graph, and for every ready work take the
        sections and floors where it is not finished, up to the contractor's floor limit.

        A re-run replaces the whole day, manual positions included, which is why it needs
        `force`; the caller is expected to have confirmed with the user first. The day is
        replaced only once the new one is built: Raport is read first, and the delete and the
        insert share one short transaction — so neither a failure in between nor an empty
        answer from Raport can leave the day empty.

        `reasons` explains an empty result in the spec's own wording.
        """
        reasons: List[str] = []
        await self.log_action(
            ActionType.PLAN_GENERATE,
            housing_id,
            actor,
            {"date": str(target_date), "section_id": str(section_id) if section_id else None, "force": force},
        )

        housing = await self.housing_manager.get_by_id(housing_id)
        if not housing:
            reasons.append("Корпус с таким id не найден.")
            return [], reasons

        scope: dict = {"housing_id": housing_id, "date": target_date}
        if section_id:
            scope["section_id"] = section_id

        existing = await self.plan_item_manager.search(**scope)
        if existing and not force:
            return existing, reasons

        housing_nodes, section_nodes = await self._load_tech_nodes(housing_id)
        if not housing_nodes and not section_nodes:
            reasons.append(
                "Не удалось сформировать план-наряд: для выбранного корпуса не сформирован "
                "календарный план. Сформируйте календарный план и повторите генерацию."
            )
            return [], reasons

        section_filters: dict = {"housing_id": housing_id}
        if section_id:
            section_filters["id"] = section_id
        sections = await self.section_manager.search(order_by=["section_number"], **section_filters)
        if not sections:
            reasons.append("У корпуса нет секций.")
            return [], reasons

        every_work = set(housing_nodes) | {w for nodes in section_nodes.values() for w in nodes}
        slice_ = await self.report_cells.get_housing_slice(housing_id, work_ids=list(every_work))
        assignments = await self.contractor_works.get_housing_assignments(housing_id)
        limits = await self._floor_limits()

        works = {w.id: w for w in await self.work_manager.get_by_ids(list(every_work))}

        plan_rows: list[dict] = []
        floors_taken: dict[tuple[UUID, UUID], int] = {}
        missing_contractor: list[str] = []

        for section in sections:
            nodes = section_nodes.get(section.id) or housing_nodes
            if not nodes:
                continue
            floors = await self.floor_manager.search(section_id=section.id, order_by=["floor_number"])

            ready_by_floor = {floor.id: set(self._ready_works(nodes, section.id, floor.id, slice_)) for floor in floors}
            frontier = sorted(
                {work_id for ready in ready_by_floor.values() for work_id in ready},
                key=lambda w: nodes[w].order,
            )

            for work_id in frontier:
                node = nodes[work_id]
                ordered = self._order_floors(floors, node.floor_sorting_direction)
                for floor in ordered:
                    if work_id not in ready_by_floor[floor.id]:
                        continue

                    contractor_id = assignments.single_contractor_for(section.id, floor.id, work_id)
                    if contractor_id is None:
                        work = works.get(work_id)
                        missing_contractor.append(
                            f"Не удалось сгенерировать план на {target_date}. Не назначен подрядчик для работы "
                            f"{work.name if work else work_id} секция {section.name} этаж {floor_label(floor)}. "
                            "Добавьте назначение в системе Рапорт."
                        )
                        continue

                    limit = self._limit_for(limits, contractor_id, work_id)
                    taken = floors_taken.get((contractor_id, work_id), 0)
                    if taken >= limit:
                        continue

                    state = slice_.cells.get(CellKey(section.id, floor.id, work_id, contractor_id))
                    plan_rows.append(
                        {
                            "date": target_date,
                            "housing_id": housing_id,
                            "section_id": section.id,
                            "floor_id": floor.id,
                            "work_id": work_id,
                            "contractor_id": contractor_id,
                            "source_percent": state.percent if state else None,
                            "work_cell_contractor_id": state.work_cell_contractor_id if state else None,
                            "work_cell_id": state.work_cell_id if state else None,
                            "source": PlanSource.AUTO,
                            "status": PlanStatus.DRAFT,
                        }
                    )
                    floors_taken[(contractor_id, work_id)] = taken + 1

        if existing and not plan_rows and not slice_.cells:
            reasons.append(
                "Рапорт не вернул ни одной ячейки шахматки по корпусу — существующий план-наряд оставлен без изменений."
            )
            return [], reasons

        if existing:
            await self.plan_item_manager.bulk_delete([item.id for item in existing])
        if plan_rows:
            await self.plan_item_manager.bulk_insert(plan_rows, is_commit=True)
            reasons.extend(dict.fromkeys(missing_contractor))
            return await self.plan_item_manager.search(**scope), reasons
        await self.db.commit()

        # Nothing generated — say why, in the spec's wording where it has one.
        reasons.extend(dict.fromkeys(missing_contractor))
        if slice_.skipped:
            reasons.append(
                "Часть ячеек Рапорта пропущена, т.к. сущности не синхронизированы: "
                + ", ".join(f"{k}={v}" for k, v in slice_.skipped.items())
            )
        if not reasons:
            reasons.append("Все работы по корпусу уже закрыты либо ожидают завершения предшественников.")
        return [], reasons

    @staticmethod
    def _order_floors(floors: list, direction: str) -> list:
        """Floors in the order the work travels through them (Р6a)."""
        return sorted(
            floors,
            key=lambda f: f.floor_number,
            reverse=direction == FloorSortingDirection.DESC.value,
        )


async def get_plan_service(db: AsyncSession = Depends(get_session)) -> AutogenerationService:
    return AutogenerationService(db=db)
