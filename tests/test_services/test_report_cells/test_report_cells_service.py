"""Chessboard slice assembly, with Raport mocked out.

Fixture raport ids (see tests/dump_data/dumps/):
  housing 1   → 10000000-0000-0000-0000-000000000001
  section 1/2 → 20000000-...-001 / -002
  floor 1/2   → 30000000-...-001 / -002
  contractor  → 40000000-...-001 / -002
  work 1/2    → 60000000-...-001 / -002
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.services.report_cells import CellKey, ReportCellsService

HOUSING_1 = UUID("11111111-1111-1111-1111-111111111111")
SECTION_1 = UUID("33333333-3333-3333-3333-333333333333")
FLOOR_1 = UUID("55555555-5555-5555-5555-555555555555")
FLOOR_2 = UUID("66666666-6666-6666-6666-666666666666")
WORK_1 = UUID("88888888-8888-8888-8888-888888888888")
CONTRACTOR_1 = UUID("99999999-9999-9999-9999-999999999999")
CONTRACTOR_2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

RAPORT_SECTION_1 = "20000000-0000-0000-0000-000000000001"
RAPORT_FLOOR_1 = "30000000-0000-0000-0000-000000000001"
RAPORT_FLOOR_2 = "30000000-0000-0000-0000-000000000002"
RAPORT_CONTRACTOR_1 = "40000000-0000-0000-0000-000000000001"
RAPORT_CONTRACTOR_2 = "40000000-0000-0000-0000-000000000002"

WCC_1 = "aaaa0000-0000-0000-0000-000000000001"
WCC_2 = "aaaa0000-0000-0000-0000-000000000002"
CELL_1 = "cccc0000-0000-0000-0000-000000000001"


def _cell(floor_raport_id: str, percent: float, contractors: list[dict], cell_id: str = CELL_1) -> dict:
    """One row of `GET /work-cells/{housing}/work/{work}` → data[]."""
    return {
        "section": {"id": RAPORT_SECTION_1, "name": "Секция 1"},
        "floor": {"id": floor_raport_id, "name": "Этаж"},
        "work_cell_id": cell_id,
        "percent_fact": percent,
        "lifecycle_status": {"id": None, "name": "В работе", "is_done": False},
        "work_cell_contractors_data": contractors,
    }


def _contractor(wcc_id: str, raport_contractor_id: str, percent: float | None = None) -> dict:
    """One element of `work_cell_contractors_data[]`; `percent` is the contractor's own."""
    return {
        "id": wcc_id,
        "contractor": {"id": raport_contractor_id, "name": "ООО"},
        "contract": None,
        "percent": percent,
    }


def _report_mock(cells: list[dict]) -> MagicMock:
    """ReportApi mock — one endpoint now carries everything, including the percent."""
    mock = MagicMock()
    mock.get_housing_work_cells_by_work = AsyncMock(return_value={"overall": {}, "data": cells})
    return mock


@pytest.mark.smoke
async def test_slice_maps_raport_ids_to_local_ones(async_test_session):
    mock = _report_mock([_cell(RAPORT_FLOOR_1, 40.0, [_contractor(WCC_1, RAPORT_CONTRACTOR_1)])])
    service = ReportCellsService(async_test_session, report=mock)

    result = await service.get_housing_slice(HOUSING_1, work_ids=[WORK_1])

    key = CellKey(section_id=SECTION_1, floor_id=FLOOR_1, work_id=WORK_1, contractor_id=CONTRACTOR_1)
    assert list(result.cells) == [key]
    state = result.cells[key]
    assert state.percent == Decimal("40")
    assert state.is_done is False
    assert state.work_cell_contractor_id == UUID(WCC_1)
    assert state.work_cell_id == UUID(CELL_1)
    assert result.skipped == {}


async def test_per_contractor_percent_wins_over_cell_percent(async_test_session):
    """The contractor's own percent takes precedence over the cell-level one (Р0)."""
    mock = _report_mock([_cell(RAPORT_FLOOR_1, 40.0, [_contractor(WCC_1, RAPORT_CONTRACTOR_1, percent=75.5)])])
    service = ReportCellsService(async_test_session, report=mock)

    result = await service.get_housing_slice(HOUSING_1, work_ids=[WORK_1])

    key = CellKey(SECTION_1, FLOOR_1, WORK_1, CONTRACTOR_1)
    assert result.cells[key].percent == Decimal("75.5")


async def test_two_contractors_on_one_cell_keep_own_percents(async_test_session):
    """One work on one floor split between contractors — the case Р0 exists for."""
    mock = _report_mock(
        [
            _cell(
                RAPORT_FLOOR_1,
                50.0,
                [
                    _contractor(WCC_1, RAPORT_CONTRACTOR_1, percent=30.0),
                    _contractor(WCC_2, RAPORT_CONTRACTOR_2, percent=100.0),
                ],
            )
        ]
    )
    service = ReportCellsService(async_test_session, report=mock)

    result = await service.get_housing_slice(HOUSING_1, work_ids=[WORK_1])

    first = CellKey(SECTION_1, FLOOR_1, WORK_1, CONTRACTOR_1)
    second = CellKey(SECTION_1, FLOOR_1, WORK_1, CONTRACTOR_2)
    assert result.cells[first].percent == Decimal("30")
    assert result.cells[first].is_done is False
    assert result.cells[second].percent == Decimal("100")
    assert result.cells[second].is_done is True
    assert sorted(map(str, result.contractors_on(SECTION_1, FLOOR_1, WORK_1))) == sorted(
        [str(CONTRACTOR_1), str(CONTRACTOR_2)]
    )


async def test_is_done_follows_lifecycle_status_flag(async_test_session):
    """Raport may mark a cell finished below 100% — the flag wins."""
    cell = _cell(RAPORT_FLOOR_1, 80.0, [_contractor(WCC_1, RAPORT_CONTRACTOR_1)])
    cell["lifecycle_status"] = {"name": "Принято", "is_done": True}
    service = ReportCellsService(async_test_session, report=_report_mock([cell]))

    result = await service.get_housing_slice(HOUSING_1, work_ids=[WORK_1])

    assert result.cells[CellKey(SECTION_1, FLOOR_1, WORK_1, CONTRACTOR_1)].is_done is True


async def test_unsynced_entities_are_skipped_and_counted(async_test_session):
    """A cell we cannot map must be reported, not silently dropped."""
    unknown_floor = _cell("30000000-0000-0000-0000-000000000999", 10.0, [_contractor(WCC_1, RAPORT_CONTRACTOR_1)])
    unknown_contractor = _cell(RAPORT_FLOOR_2, 10.0, [_contractor(WCC_2, "40000000-0000-0000-0000-000000000999")])
    service = ReportCellsService(async_test_session, report=_report_mock([unknown_floor, unknown_contractor]))

    result = await service.get_housing_slice(HOUSING_1, work_ids=[WORK_1])

    assert result.cells == {}
    assert result.skipped == {"floor_not_synced": 1, "contractor_not_synced": 1}


async def test_empty_raport_response_yields_empty_slice(async_test_session):
    service = ReportCellsService(async_test_session, report=_report_mock([]))

    result = await service.get_housing_slice(HOUSING_1, work_ids=[WORK_1])

    assert result.cells == {}
    assert result.skipped == {}


async def test_raport_failure_on_one_work_does_not_lose_the_housing(async_test_session):
    """A broken work is logged and skipped; the rest of the housing still comes through."""
    mock = _report_mock([])
    mock.get_housing_work_cells_by_work = AsyncMock(side_effect=RuntimeError("Raport 500"))
    service = ReportCellsService(async_test_session, report=mock)

    result = await service.get_housing_slice(HOUSING_1, work_ids=[WORK_1])

    assert result.cells == {}


async def test_single_object_data_is_tolerated(async_test_session):
    """The OpenAPI schema declares `data` as one object; the handler returns a list."""
    mock = _report_mock([])
    mock.get_housing_work_cells_by_work = AsyncMock(
        return_value={"data": _cell(RAPORT_FLOOR_1, 25.0, [_contractor(WCC_1, RAPORT_CONTRACTOR_1)])}
    )
    service = ReportCellsService(async_test_session, report=mock)

    result = await service.get_housing_slice(HOUSING_1, work_ids=[WORK_1])

    assert result.cells[CellKey(SECTION_1, FLOOR_1, WORK_1, CONTRACTOR_1)].percent == Decimal("25")


async def test_housing_without_raport_id_is_reported(async_test_session):
    """Housing 2 is in the fixtures with a raport_id; an unknown id has none at all."""
    service = ReportCellsService(async_test_session, report=_report_mock([]))

    result = await service.get_housing_slice(UUID("00000000-0000-0000-0000-000000000000"))

    assert result.cells == {}
    assert result.skipped == {"housing_not_synced": 1}


# ── Which works apply to a floor ──────────────────────────────────────────────

RAPORT_WORK_1 = "60000000-0000-0000-0000-000000000001"
RAPORT_WORK_2 = "60000000-0000-0000-0000-000000000002"


def _section_row(work_raport_id: str, cells: list[dict]) -> dict:
    """One row of `GET /work-cells/section/{id}` → data[]: a work with its cells."""
    return {
        "id": work_raport_id,
        "name": "Устройство ограждения котлована",
        "work_type": {"id": "b0e6e68a-bf74-48d7-b21c-f7b27fdc393e", "name": "Устройство котлована"},
        "work_group": {"id": "6dc469bb-59a4-4293-8edd-db55c5a128ed", "name": "Земляные работы"},
        "work_cells": cells,
    }


def _section_cell(floor_raport_id: str, is_enabled: bool | None = True) -> dict:
    cell = {"floor": {"id": floor_raport_id, "name": "Этаж"}, "work_cell_id": CELL_1}
    if is_enabled is not None:
        cell["is_enabled"] = is_enabled
    return cell


def _section_mock(rows: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.list_all = AsyncMock(return_value=rows)
    return mock


class TestWorksOnFloor:
    async def test_keeps_only_the_works_present_on_that_floor(self, async_test_session):
        rows = [
            _section_row(RAPORT_WORK_1, [_section_cell(RAPORT_FLOOR_1), _section_cell(RAPORT_FLOOR_2)]),
            _section_row(RAPORT_WORK_2, [_section_cell(RAPORT_FLOOR_2)]),
        ]
        service = ReportCellsService(async_test_session, report=_section_mock(rows))

        assert await service.works_on_floor(RAPORT_SECTION_1, RAPORT_FLOOR_1) == {RAPORT_WORK_1}

    async def test_a_disabled_cell_does_not_count(self, async_test_session):
        rows = [_section_row(RAPORT_WORK_1, [_section_cell(RAPORT_FLOOR_1, is_enabled=False)])]
        service = ReportCellsService(async_test_session, report=_section_mock(rows))

        assert await service.works_on_floor(RAPORT_SECTION_1, RAPORT_FLOOR_1) == set()

    async def test_a_missing_flag_counts_as_enabled(self, async_test_session):
        rows = [_section_row(RAPORT_WORK_1, [_section_cell(RAPORT_FLOOR_1, is_enabled=None)])]
        service = ReportCellsService(async_test_session, report=_section_mock(rows))

        assert await service.works_on_floor(RAPORT_SECTION_1, RAPORT_FLOOR_1) == {RAPORT_WORK_1}

    async def test_an_empty_answer_is_an_answer(self, async_test_session):
        # Distinct from None: the floor genuinely has nothing to offer.
        service = ReportCellsService(async_test_session, report=_section_mock([]))

        assert await service.works_on_floor(RAPORT_SECTION_1, RAPORT_FLOOR_1) == set()

    async def test_none_when_raport_fails(self, async_test_session):
        from src.external.report.api import ReportApiError

        mock = MagicMock()
        mock.list_all = AsyncMock(side_effect=ReportApiError(500, "boom"))
        service = ReportCellsService(async_test_session, report=mock)

        assert await service.works_on_floor(RAPORT_SECTION_1, RAPORT_FLOOR_1) is None

    async def test_rows_without_a_work_id_are_skipped(self, async_test_session):
        rows = [{"name": "битая строка", "work_cells": [_section_cell(RAPORT_FLOOR_1)]}]
        service = ReportCellsService(async_test_session, report=_section_mock(rows))

        assert await service.works_on_floor(RAPORT_SECTION_1, RAPORT_FLOOR_1) == set()
