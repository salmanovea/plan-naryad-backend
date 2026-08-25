"""The public feed Raport reads to light up cells in «Задание на день».

Everything crossing this boundary is a Raport id — Raport does not know our UUIDs. Fixture
raport ids are listed in tests/test_services/test_report_cells/.
"""

from datetime import date
from uuid import UUID

import pytest

from src.models import managers
from src.models.dbo.tables.plan import PlanStatus
from src.services.plan.service import AutogenerationService

HOUSING = UUID("11111111-1111-1111-1111-111111111111")
SECTION_1 = UUID("33333333-3333-3333-3333-333333333333")
SECTION_2 = UUID("44444444-4444-4444-4444-444444444444")
FLOOR_1 = UUID("55555555-5555-5555-5555-555555555555")
WORK_A = UUID("88888888-8888-8888-8888-888888888888")
CONTRACTOR = UUID("99999999-9999-9999-9999-999999999999")

RAPORT_HOUSING = "10000000-0000-0000-0000-000000000001"
RAPORT_SECTION_1 = "20000000-0000-0000-0000-000000000001"
RAPORT_SECTION_2 = "20000000-0000-0000-0000-000000000002"
RAPORT_FLOOR_1 = "30000000-0000-0000-0000-000000000001"
RAPORT_CONTRACTOR = "40000000-0000-0000-0000-000000000001"
RAPORT_WORK_A = "60000000-0000-0000-0000-000000000001"

WCC = UUID("cccc0000-0000-0000-0000-00000000dd01")
CELL = UUID("cccc0000-0000-0000-0000-00000000dd02")
TARGET = date(2026, 7, 1)


async def _position(session, *, status: str, section_id: UUID = SECTION_1) -> UUID:
    item = await managers.PlanItemManager(session).create(
        {
            "date": TARGET,
            "housing_id": HOUSING,
            "section_id": section_id,
            "floor_id": FLOOR_1,
            "work_id": WORK_A,
            "contractor_id": CONTRACTOR,
            "work_cell_contractor_id": WCC,
            "work_cell_id": CELL,
            "source": "auto",
            "status": status,
        }
    )
    return item.id


async def _clear(session) -> None:
    plans = managers.PlanItemManager(session)
    for item in await plans.search(housing_id=HOUSING, date=TARGET):
        await plans.delete_by_id(item.id)


@pytest.mark.smoke
async def test_transferred_position_is_returned_in_raport_ids(async_test_session):
    await _clear(async_test_session)
    plan_item_id = await _position(async_test_session, status=PlanStatus.TRANSFERRED.value)
    service = AutogenerationService(async_test_session)

    rows = await service.daily_assignment(RAPORT_HOUSING, TARGET)

    assert len(rows) == 1
    row = rows[0]
    assert row["plan_item_id"] == plan_item_id
    assert row["work_cell_contractor_id"] == WCC
    assert row["work_cell_id"] == CELL
    # Local UUIDs must not leak — every reference is Raport's own id.
    assert row["section_id"] == RAPORT_SECTION_1
    assert row["floor_id"] == RAPORT_FLOOR_1
    assert row["work_id"] == RAPORT_WORK_A
    assert row["contractor_id"] == RAPORT_CONTRACTOR
    assert row["status"] == PlanStatus.TRANSFERRED


async def test_draft_and_confirmed_are_not_exposed(async_test_session):
    """The toggle follows «Передано подрядчику» — nothing earlier counts."""
    await _clear(async_test_session)
    await _position(async_test_session, status=PlanStatus.DRAFT.value)
    await _position(async_test_session, status=PlanStatus.CONFIRMED.value, section_id=SECTION_2)
    service = AutogenerationService(async_test_session)

    rows = await service.daily_assignment(RAPORT_HOUSING, TARGET)

    assert rows == []


async def test_section_filter_narrows_to_the_per_section_view(async_test_session):
    await _clear(async_test_session)
    await _position(async_test_session, status=PlanStatus.TRANSFERRED.value, section_id=SECTION_1)
    await _position(async_test_session, status=PlanStatus.TRANSFERRED.value, section_id=SECTION_2)
    service = AutogenerationService(async_test_session)

    only_first = await service.daily_assignment(RAPORT_HOUSING, TARGET, section_raport_id=RAPORT_SECTION_1)
    both = await service.daily_assignment(RAPORT_HOUSING, TARGET)

    assert [r["section_id"] for r in only_first] == [RAPORT_SECTION_1]
    assert len(both) == 2


async def test_empty_day_is_a_valid_answer(async_test_session):
    """An empty list tells Raport the toggle should be inactive."""
    await _clear(async_test_session)
    service = AutogenerationService(async_test_session)

    rows = await service.daily_assignment(RAPORT_HOUSING, date(2026, 7, 2))

    assert rows == []


async def test_unknown_housing_returns_empty(async_test_session):
    service = AutogenerationService(async_test_session)

    rows = await service.daily_assignment("00000000-0000-0000-0000-000000000999", TARGET)

    assert rows == []


async def test_unknown_section_returns_empty(async_test_session):
    """A section id Raport knows but we have not synced must not silently widen the scope."""
    await _clear(async_test_session)
    await _position(async_test_session, status=PlanStatus.TRANSFERRED.value)
    service = AutogenerationService(async_test_session)

    rows = await service.daily_assignment(
        RAPORT_HOUSING, TARGET, section_raport_id="20000000-0000-0000-0000-000000000999"
    )

    assert rows == []


@pytest.mark.smoke
async def test_endpoint_speaks_raport_ids(client, async_test_session):
    await _clear(async_test_session)
    await _position(async_test_session, status=PlanStatus.TRANSFERRED.value)

    from tests.constants import API

    response = await client.get(
        f"{API}/plan-naryad/daily-assignment",
        params={"housing_raport_id": RAPORT_HOUSING, "date": str(TARGET)},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["section_id"] == RAPORT_SECTION_1
    assert data[0]["status"] == PlanStatus.TRANSFERRED
