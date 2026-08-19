"""Reads the Raport chessboard («шахматка») and turns it into a local slice.

The unit of execution is `work_cell_contractor` — one contractor's share of one work on
one floor, each with its own percent (decision Р0 in docs/to-be-plan.md). Plan generation
and reconciliation both ask this service «what percent does this contractor have on this
cell», and neither should know anything about Raport's response shapes.

One Raport endpoint covers it: `GET /work-cells/{housing_id}/work/{work_id}` ties a cell to
a **work**, names the contractor and — since the Raport change of 17 Aug 2026 — carries that
contractor's own `percent` inside `work_cell_contractors_data[]`. Before that change the
per-contractor percent had to be joined in from `GET /work-cells/section/{section_id}`, which
cost four extra requests per housing.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_session
from src.external.report.api import ReportApi, ReportApiError
from src.models import managers
from src.models.managers.common import BaseManager
from src.services.common import BaseService

log = LoggerProvider().get_logger(__name__)

DONE_PERCENT = Decimal("100")


@dataclass(frozen=True)
class CellKey:
    """Identity of a work cell as this project sees it — all ids are local UUIDs."""

    section_id: UUID
    floor_id: UUID
    work_id: UUID
    contractor_id: UUID


@dataclass
class CellState:
    """Completion of one contractor on one cell."""

    percent: Decimal
    is_done: bool
    work_cell_contractor_id: UUID
    work_cell_id: Optional[UUID] = None


@dataclass
class HousingSlice:
    """Everything known about a housing's chessboard at one point in time.

    `skipped` counts cells dropped because a Raport entity has no local counterpart.
    Silently losing floors would make a generated plan look complete when it is not, so
    the counters travel with the data and are logged by the caller.
    """

    cells: dict[CellKey, CellState] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    # Built on first use: (section, floor, work) → states of every contractor on that cell.
    # Plan generation asks «is this cell finished» inside nested loops, and a housing holds
    # tens of thousands of cells — scanning them each time would dominate the run.
    _by_cell: Optional[dict[tuple[UUID, UUID, UUID], list[CellState]]] = None

    def states_on(self, section_id: UUID, floor_id: UUID, work_id: UUID) -> list[CellState]:
        """Every contractor's state on one cell."""
        if self._by_cell is None:
            index: dict[tuple[UUID, UUID, UUID], list[CellState]] = {}
            for key, state in self.cells.items():
                index.setdefault((key.section_id, key.floor_id, key.work_id), []).append(state)
            self._by_cell = index
        return self._by_cell.get((section_id, floor_id, work_id), [])

    def percent_for(self, key: CellKey) -> Optional[Decimal]:
        state = self.cells.get(key)
        return state.percent if state else None

    def is_done(self, key: CellKey) -> bool:
        state = self.cells.get(key)
        return bool(state and state.is_done)

    def contractors_on(self, section_id: UUID, floor_id: UUID, work_id: UUID) -> list[UUID]:
        """Contractors present on a cell — usually one, occasionally several (Р0)."""
        return [
            key.contractor_id
            for key in self.cells
            if key.section_id == section_id and key.floor_id == floor_id and key.work_id == work_id
        ]


def _to_decimal(value: Any) -> Decimal:
    """Raport sends percents as floats; keep them exact and never return None."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _nested_id(payload: Any, *keys: str) -> Optional[str]:
    """Pull a nested id out of a Raport row, tolerating nulls at any level."""
    node = payload
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return str(node) if node else None


class ReportCellsService(BaseService):
    _RESOLVE_CHUNK = 500

    def __init__(self, db: AsyncSession, report: Optional[ReportApi] = None):
        self.db = db
        self.report = report or ReportApi()
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.work_manager = managers.WorkManager(db)
        self.contractor_manager = managers.ContractorManager(db)

    async def get_housing_slice(self, housing_id: UUID, work_ids: Optional[list[UUID]] = None) -> HousingSlice:
        """Build the chessboard slice for a housing.

        `work_ids` narrows the query to specific local works — plan generation passes the
        housing's technological sequence, which keeps this to ~13 requests instead of the
        whole catalogue. Passing None means every work that has a local `raport_id`.
        """
        result = HousingSlice(skipped={})

        housing = await self.housing_manager.get_by_id(housing_id)
        if not housing or not housing.raport_id:
            log.warning("report_cells: housing %s has no raport_id — nothing to read", housing_id)
            result.skipped["housing_not_synced"] = 1
            return result

        works = await self._works_to_query(work_ids)
        if not works:
            log.info("report_cells: no works with a raport_id to query for housing %s", housing_id)
            return result

        section_map = await self._reverse_map(self.section_manager, housing_id=housing_id)
        floor_map = await self._floor_map(housing_id)

        # Fetch first, resolve contractors second: there are ~48k contractors in total but
        # only a handful appear on one housing, so the map is built from what was seen.
        rows_by_work: dict[str, list[dict]] = {}
        seen_contractors: set[str] = set()
        for work_raport_id in works:
            rows = await self._fetch_work_cells(housing.raport_id, work_raport_id)
            rows_by_work[work_raport_id] = rows
            for row in rows:
                for wcc in row.get("work_cell_contractors_data") or []:
                    contractor_raport_id = _nested_id(wcc, "contractor", "id")
                    if contractor_raport_id:
                        seen_contractors.add(contractor_raport_id)
        contractor_map = await self._resolve_contractors(seen_contractors)

        skipped_section = skipped_floor = skipped_contractor = 0
        for work_raport_id, local_work_id in works.items():
            for row in rows_by_work.get(work_raport_id, []):
                section_raport_id = _nested_id(row, "section", "id")
                floor_raport_id = _nested_id(row, "floor", "id")
                local_section_id = section_map.get(section_raport_id) if section_raport_id else None
                local_floor_id = floor_map.get(floor_raport_id) if floor_raport_id else None
                if local_section_id is None:
                    skipped_section += 1
                    continue
                if local_floor_id is None:
                    skipped_floor += 1
                    continue

                cell_percent = _to_decimal(row.get("percent_fact"))
                work_cell_id = row.get("work_cell_id")
                cell_uuid = UUID(str(work_cell_id)) if work_cell_id else None

                for wcc in row.get("work_cell_contractors_data") or []:
                    contractor_raport_id = _nested_id(wcc, "contractor", "id")
                    local_contractor_id = contractor_map.get(contractor_raport_id) if contractor_raport_id else None
                    if local_contractor_id is None:
                        skipped_contractor += 1
                        continue

                    wcc_id = wcc.get("id")
                    if not wcc_id:
                        continue
                    wcc_uuid = UUID(str(wcc_id))

                    percent = _to_decimal(wcc["percent"]) if wcc.get("percent") is not None else cell_percent
                    result.cells[
                        CellKey(
                            section_id=local_section_id,
                            floor_id=local_floor_id,
                            work_id=local_work_id,
                            contractor_id=local_contractor_id,
                        )
                    ] = CellState(
                        percent=percent,
                        is_done=self._is_done(percent, row.get("lifecycle_status")),
                        work_cell_contractor_id=wcc_uuid,
                        work_cell_id=cell_uuid,
                    )

        if skipped_section:
            result.skipped["section_not_synced"] = skipped_section
        if skipped_floor:
            result.skipped["floor_not_synced"] = skipped_floor
        if skipped_contractor:
            result.skipped["contractor_not_synced"] = skipped_contractor
        if result.skipped:
            log.warning("report_cells: housing %s — skipped cells: %s", housing_id, result.skipped)
        log.info("report_cells: housing %s — %d cell/contractor pairs read", housing_id, len(result.cells))

        return result

    async def works_on_floor(self, section_raport_id: str, floor_raport_id: str) -> Optional[set[str]]:
        """Raport ids of works that have a cell on that floor, or None when Raport cannot answer.

        `GET /work-cells/section/{id}` returns a work per row with its `work_cells[]`, each cell
        naming a floor — the only Raport endpoint that says which works apply where. It used to
        answer 500 on every section, which is why the manual-add dialog long offered the works of
        a whole area; Raport fixed it on 17 Aug 2026.

        None (rather than an empty set) means «could not find out»: the caller then offers the
        wider list instead of an empty one, because an outage must not look like «no work here».
        """
        try:
            rows = await self.report.list_all("list_section_work_cells", section_id=UUID(section_raport_id))
        except (ReportApiError, ValueError, RuntimeError) as err:
            log.warning("report_cells: cannot read cells of section %s: %s", section_raport_id, err)
            return None

        works: set[str] = set()
        for row in rows:
            work_raport_id = row.get("id")
            if not work_raport_id:
                continue
            for cell in row.get("work_cells") or []:
                if cell.get("is_enabled") is False:
                    continue
                if _nested_id(cell, "floor", "id") == floor_raport_id:
                    works.add(str(work_raport_id))
                    break
        return works

    @staticmethod
    def _is_done(percent: Decimal, lifecycle_status: Any) -> bool:
        """A cell counts as finished at 100%, or when Raport marks the status done."""
        if isinstance(lifecycle_status, dict) and lifecycle_status.get("is_done"):
            return True
        return percent >= DONE_PERCENT

    async def _fetch_work_cells(self, housing_raport_id: str, work_raport_id: str) -> list[dict]:
        """One work's cells across the housing; an empty list when Raport has none.

        A failure on one work must not lose the whole housing, so the error is logged and
        that work is skipped.
        """
        try:
            response = await self.report.get_housing_work_cells_by_work(
                housing_id=UUID(housing_raport_id),
                work_id=UUID(work_raport_id),
            )
        except Exception as err:
            log.error("report_cells: failed to read cells for work %s: %s", work_raport_id, err)
            return []

        data = (response or {}).get("data")
        if isinstance(data, dict):  # schema declares a single object; handler returns a list
            return [data]
        return data or []

    async def _works_to_query(self, work_ids: Optional[list[UUID]]) -> dict[str, UUID]:
        """{work raport_id: local work id} for the works to be queried."""
        if work_ids:
            works = await self.work_manager.get_by_ids(list(set(work_ids)))
        else:
            works = await self.work_manager.search()
        return {w.raport_id: w.id for w in works if w.raport_id}

    async def _floor_map(self, housing_id: UUID) -> dict[str, UUID]:
        """{floor raport_id: local floor id} for every floor of the housing."""
        sections = await self.section_manager.search(housing_id=housing_id)
        section_ids = [s.id for s in sections]
        if not section_ids:
            return {}
        floors = await self.floor_manager.search(section_id__in=section_ids)
        return {f.raport_id: f.id for f in floors if f.raport_id}

    async def _reverse_map(self, manager: BaseManager, **filters: Any) -> dict[str, UUID]:
        """{raport_id: local id} for a whole (optionally filtered) table."""
        rows = await manager.search(**filters)
        return {row.raport_id: row.id for row in rows if getattr(row, "raport_id", None)}

    async def _resolve_contractors(self, raport_ids: Iterable[str]) -> dict[str, UUID]:
        """{contractor raport_id: local id}, queried in chunks for only the ids seen."""
        ids = sorted({rid for rid in raport_ids if rid})
        resolved: dict[str, UUID] = {}
        for start in range(0, len(ids), self._RESOLVE_CHUNK):
            chunk = ids[start : start + self._RESOLVE_CHUNK]
            rows = await self.contractor_manager.search(raport_id__in=chunk)
            for row in rows:
                if row.raport_id:
                    resolved[row.raport_id] = row.id
        return resolved


async def get_report_cells_service(db: AsyncSession = Depends(get_session)) -> ReportCellsService:
    return ReportCellsService(db=db)
