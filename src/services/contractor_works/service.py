"""Contractor assignments, read from Raport on demand and never stored (decision Р1).

The local table was ~34k aggregated rows; the detailed source is ~1.2M (20 402 floors ×
~59 works). Assignments feed exactly two point-in-time operations — plan generation and the
manual-add dropdown — and appear in no list or filter, so synchronising them would buy
nothing. See docs/to-be-plan.md Р1.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_session
from src.external.report.api import ReportApi
from src.models import managers
from src.services.common import BaseService, end_transaction

log = LoggerProvider().get_logger(__name__)


@dataclass(frozen=True)
class AssignmentKey:
    """(section, floor, work) — the grain Raport assigns contractors at."""

    section_id: UUID
    floor_id: UUID
    work_id: UUID


@dataclass
class HousingAssignments:
    """Assignments of one housing, ready for the generator to look into.

    `skipped` counts rows dropped because a Raport entity is not synced locally — the same
    reasoning as in `report_cells`: a silently thinner plan is worse than a logged gap.
    """

    by_cell: dict[AssignmentKey, list[UUID]] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)

    def contractors_for(self, section_id: UUID, floor_id: UUID, work_id: UUID) -> list[UUID]:
        return self.by_cell.get(AssignmentKey(section_id, floor_id, work_id), [])

    def single_contractor_for(self, section_id: UUID, floor_id: UUID, work_id: UUID) -> Optional[UUID]:
        """The assigned contractor, or None when nobody — or more than one — is assigned.

        Ambiguity is deliberately not guessed away: the caller decides whether to skip the
        position or ask the user.
        """
        contractors = self.contractors_for(section_id, floor_id, work_id)
        return contractors[0] if len(contractors) == 1 else None


def _nested_id(payload: Any, *keys: str) -> Optional[str]:
    node = payload
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return str(node) if node else None


class ContractorWorksService(BaseService):
    _RESOLVE_CHUNK = 500
    _PER_PAGE = 200

    def __init__(self, db: AsyncSession, report: Optional[ReportApi] = None):
        self.db = db
        self.report = report or ReportApi()
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.work_manager = managers.WorkManager(db)
        self.contractor_manager = managers.ContractorManager(db)

    async def get_housing_assignments(self, housing_id: UUID) -> HousingAssignments:
        """Every assignment on a housing — one paginated Raport query, ~2400 rows."""
        result = HousingAssignments(skipped={})

        housing = await self.housing_manager.get_by_id(housing_id)
        if not housing or not housing.raport_id:
            log.warning("contractor_works: housing %s has no raport_id", housing_id)
            result.skipped["housing_not_synced"] = 1
            return result

        await end_transaction(self.db)
        rows = await self._fetch_all(housing_id=UUID(housing.raport_id))
        await self._fill(result, rows, housing_id)
        log.info(
            "contractor_works: housing %s — %d cells with assignments%s",
            housing_id,
            len(result.by_cell),
            f", skipped {result.skipped}" if result.skipped else "",
        )
        return result

    async def get_contractors_for_cell(self, work_id: UUID, floor_id: UUID) -> list[UUID]:
        """Contractors assigned to a work on a floor — the manual-add dropdown (ТЗ)."""
        work = await self.work_manager.get_by_id(work_id)
        floor = await self.floor_manager.get_by_id(floor_id)
        if not work or not work.raport_id or not floor or not floor.raport_id:
            return []

        await end_transaction(self.db)
        rows = await self._fetch_all(work_id=UUID(work.raport_id), floor_id=UUID(floor.raport_id))
        contractor_raport_ids = {rid for rid in (_nested_id(r, "contractor", "id") for r in rows) if rid}
        contractor_map = await self._resolve(self.contractor_manager, contractor_raport_ids)
        return sorted(contractor_map.values(), key=str)

    async def _fill(self, result: HousingAssignments, rows: list[dict], housing_id: UUID) -> None:
        """Resolve Raport ids to local ones and group by cell."""
        section_map = await self._reverse_map(self.section_manager, housing_id=housing_id)
        floor_map = await self._floor_map(housing_id)
        work_map = await self._resolve(
            self.work_manager, {rid for rid in (_nested_id(r, "work", "id") for r in rows) if rid}
        )
        contractor_map = await self._resolve(
            self.contractor_manager, {rid for rid in (_nested_id(r, "contractor", "id") for r in rows) if rid}
        )

        skipped: dict[str, int] = {}
        for row in rows:
            section_id = section_map.get(_nested_id(row, "section", "id") or "")
            floor_id = floor_map.get(_nested_id(row, "floor", "id") or "")
            work_id = work_map.get(_nested_id(row, "work", "id") or "")
            contractor_id = contractor_map.get(_nested_id(row, "contractor", "id") or "")

            # Assignments above floor level exist in Raport (planning_type SECTION/HOUSING);
            # they carry no floor and cannot be attached to a plan position.
            for name, value in (
                ("section_not_synced", section_id),
                ("floor_missing_or_not_synced", floor_id),
                ("work_not_synced", work_id),
                ("contractor_not_synced", contractor_id),
            ):
                if value is None:
                    skipped[name] = skipped.get(name, 0) + 1
                    break
            else:
                key = AssignmentKey(section_id, floor_id, work_id)  # type: ignore[arg-type]
                bucket = result.by_cell.setdefault(key, [])
                if contractor_id not in bucket:
                    bucket.append(contractor_id)  # type: ignore[arg-type]

        result.skipped.update(skipped)

    async def _fetch_all(self, **filters: Any) -> list[dict]:
        """Walk every page of `/contractor-works` for the given filters."""
        rows: list[dict] = []
        page = 1
        while True:
            try:
                response = await self.report.list_contractor_works(page=page, per_page=self._PER_PAGE, **filters)
            except Exception as err:
                log.error("contractor_works: read failed on page %d (%s): %s", page, filters, err)
                break
            items = (response or {}).get("data") or []
            rows.extend(items)
            next_page = ((response or {}).get("pagination") or {}).get("next_page")
            if not next_page or not items:
                break
            page = next_page
        return rows

    async def _reverse_map(self, manager: Any, **filters: Any) -> dict[str, UUID]:
        rows = await manager.search(**filters)
        return {row.raport_id: row.id for row in rows if getattr(row, "raport_id", None)}

    async def _floor_map(self, housing_id: UUID) -> dict[str, UUID]:
        sections = await self.section_manager.search(housing_id=housing_id)
        section_ids = [s.id for s in sections]
        if not section_ids:
            return {}
        floors = await self.floor_manager.search(section_id__in=section_ids)
        return {f.raport_id: f.id for f in floors if f.raport_id}

    async def _resolve(self, manager: Any, raport_ids: Iterable[str]) -> dict[str, UUID]:
        ids = sorted({rid for rid in raport_ids if rid})
        resolved: dict[str, UUID] = {}
        for start in range(0, len(ids), self._RESOLVE_CHUNK):
            rows = await manager.search(raport_id__in=ids[start : start + self._RESOLVE_CHUNK])
            for row in rows:
                if row.raport_id:
                    resolved[row.raport_id] = row.id
        return resolved


async def get_contractor_works_service(db: AsyncSession = Depends(get_session)) -> ContractorWorksService:
    return ContractorWorksService(db=db)
