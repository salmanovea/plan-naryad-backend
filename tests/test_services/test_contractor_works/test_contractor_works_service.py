"""Contractor assignments read from Raport, with the HTTP client mocked out.

Assignments are never stored locally (decision Р1), so everything here is about turning a
`/contractor-works` page into local ids and refusing to guess when a cell is ambiguous.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.services.contractor_works import AssignmentKey, ContractorWorksService

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
RAPORT_WORK_1 = "60000000-0000-0000-0000-000000000001"


def _row(
    contractor_raport_id: str = RAPORT_CONTRACTOR_1,
    floor_raport_id: str | None = RAPORT_FLOOR_1,
    work_raport_id: str = RAPORT_WORK_1,
    section_raport_id: str = RAPORT_SECTION_1,
) -> dict:
    """One row of `GET /contractor-works` → data[]."""
    return {
        "id": "eeee0000-0000-0000-0000-000000000001",
        "contractor": {"id": contractor_raport_id, "name": "ООО"},
        "section": {"id": section_raport_id, "name": "Секция 1"},
        "floor": {"id": floor_raport_id, "name": "Этаж 1"} if floor_raport_id else None,
        "work": {"id": work_raport_id, "name": "Монолит"},
    }


def _report_mock(*pages: list[dict]) -> MagicMock:
    """ReportApi mock; each argument is one page of `/contractor-works`."""
    mock = MagicMock()
    responses = [
        {"data": page, "pagination": {"next_page": i + 2 if i + 1 < len(pages) else None}}
        for i, page in enumerate(pages)
    ]
    mock.list_contractor_works = AsyncMock(side_effect=responses or [{"data": [], "pagination": {}}])
    return mock


@pytest.mark.smoke
async def test_housing_assignments_group_by_cell(async_test_session):
    service = ContractorWorksService(async_test_session, report=_report_mock([_row()]))

    result = await service.get_housing_assignments(HOUSING_1)

    key = AssignmentKey(section_id=SECTION_1, floor_id=FLOOR_1, work_id=WORK_1)
    assert result.by_cell == {key: [CONTRACTOR_1]}
    assert result.skipped == {}
    assert result.single_contractor_for(SECTION_1, FLOOR_1, WORK_1) == CONTRACTOR_1


async def test_pagination_is_walked(async_test_session):
    first = [_row(floor_raport_id=RAPORT_FLOOR_1)]
    second = [_row(floor_raport_id=RAPORT_FLOOR_2)]
    service = ContractorWorksService(async_test_session, report=_report_mock(first, second))

    result = await service.get_housing_assignments(HOUSING_1)

    assert result.contractors_for(SECTION_1, FLOOR_1, WORK_1) == [CONTRACTOR_1]
    assert result.contractors_for(SECTION_1, FLOOR_2, WORK_1) == [CONTRACTOR_1]


async def test_ambiguous_cell_is_not_guessed(async_test_session):
    """Two contractors on one cell — the caller must decide, not this service."""
    rows = [_row(RAPORT_CONTRACTOR_1), _row(RAPORT_CONTRACTOR_2)]
    service = ContractorWorksService(async_test_session, report=_report_mock(rows))

    result = await service.get_housing_assignments(HOUSING_1)

    assert sorted(map(str, result.contractors_for(SECTION_1, FLOOR_1, WORK_1))) == sorted(
        [str(CONTRACTOR_1), str(CONTRACTOR_2)]
    )
    assert result.single_contractor_for(SECTION_1, FLOOR_1, WORK_1) is None


async def test_duplicate_rows_collapse(async_test_session):
    """Raport pagination can repeat a row; the same contractor must not be added twice."""
    service = ContractorWorksService(async_test_session, report=_report_mock([_row(), _row()]))

    result = await service.get_housing_assignments(HOUSING_1)

    assert result.contractors_for(SECTION_1, FLOOR_1, WORK_1) == [CONTRACTOR_1]


async def test_assignment_without_floor_is_skipped(async_test_session):
    """Raport also assigns above floor level (planning_type SECTION/HOUSING)."""
    service = ContractorWorksService(async_test_session, report=_report_mock([_row(floor_raport_id=None)]))

    result = await service.get_housing_assignments(HOUSING_1)

    assert result.by_cell == {}
    assert result.skipped == {"floor_missing_or_not_synced": 1}


async def test_unsynced_work_is_counted(async_test_session):
    unknown = _row(work_raport_id="60000000-0000-0000-0000-000000000999")
    service = ContractorWorksService(async_test_session, report=_report_mock([unknown]))

    result = await service.get_housing_assignments(HOUSING_1)

    assert result.by_cell == {}
    assert result.skipped == {"work_not_synced": 1}


async def test_raport_failure_returns_empty_instead_of_raising(async_test_session):
    mock = MagicMock()
    mock.list_contractor_works = AsyncMock(side_effect=RuntimeError("Raport 503"))
    service = ContractorWorksService(async_test_session, report=mock)

    result = await service.get_housing_assignments(HOUSING_1)

    assert result.by_cell == {}


async def test_housing_without_raport_id_is_reported(async_test_session):
    service = ContractorWorksService(async_test_session, report=_report_mock([]))

    result = await service.get_housing_assignments(UUID("00000000-0000-0000-0000-000000000000"))

    assert result.skipped == {"housing_not_synced": 1}


@pytest.mark.smoke
async def test_contractors_for_cell_feeds_the_manual_add_dropdown(async_test_session):
    service = ContractorWorksService(async_test_session, report=_report_mock([_row()]))

    contractors = await service.get_contractors_for_cell(work_id=WORK_1, floor_id=FLOOR_1)

    assert contractors == [CONTRACTOR_1]


async def test_contractors_for_cell_needs_synced_entities(async_test_session):
    """No raport_id on the work or floor → no query, empty list."""
    service = ContractorWorksService(async_test_session, report=_report_mock([_row()]))

    contractors = await service.get_contractors_for_cell(
        work_id=UUID("00000000-0000-0000-0000-000000000000"), floor_id=FLOOR_1
    )

    assert contractors == []
