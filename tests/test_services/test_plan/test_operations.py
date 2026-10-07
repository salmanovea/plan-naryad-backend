"""Operations on plan positions: manual add, confirm, delete, transfer, lookups, journal.

Raport-backed collaborators are stubbed — these tests are about the rules the spec states,
not about response shapes (those live in tests/test_services/test_report_cells/).
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.models import managers
from src.models.dbo.tables.plan import PlanStatus
from src.models.dbo.tables.settings import ActionType
from src.services.contractor_works import AssignmentKey, HousingAssignments
from src.services.plan.service import AutogenerationService
from src.services.report_cells import CellKey, CellState, HousingSlice

HOUSING = UUID("11111111-1111-1111-1111-111111111111")
SECTION_1 = UUID("33333333-3333-3333-3333-333333333333")
SECTION_2 = UUID("44444444-4444-4444-4444-444444444444")
FLOOR_1 = UUID("55555555-5555-5555-5555-555555555555")
FLOOR_2 = UUID("66666666-6666-6666-6666-666666666666")
WORK_A = UUID("88888888-8888-8888-8888-888888888888")
WORK_TYPE = UUID("77777777-7777-7777-7777-777777777777")
CONTRACTOR = UUID("99999999-9999-9999-9999-999999999999")
CONTRACTOR_2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

TARGET = date(2026, 6, 10)


def _service(
    session,
    allowed_contractors: list[UUID] | None = None,
    cells: dict | None = None,
    floor_works: set[str] | None = None,
) -> AutogenerationService:
    service = AutogenerationService(session)
    service.contractor_works = MagicMock()
    service.contractor_works.get_contractors_for_cell = AsyncMock(
        return_value=allowed_contractors if allowed_contractors is not None else [CONTRACTOR]
    )
    service.contractor_works.get_housing_assignments = AsyncMock(
        return_value=HousingAssignments(by_cell={AssignmentKey(SECTION_1, FLOOR_1, WORK_A): [CONTRACTOR]})
    )
    service.report_cells = MagicMock()
    service.report_cells.get_housing_slice = AsyncMock(return_value=HousingSlice(cells=cells or {}))
    # None means «Raport could not say which works belong to this floor» — the default here, so
    # tests that are not about narrowing see the plain calendar-plan scope.
    service.report_cells.works_on_floor = AsyncMock(return_value=floor_works)
    return service


async def _clear(session) -> None:
    plans = managers.PlanItemManager(session)
    for item in await plans.search(housing_id=HOUSING, date=TARGET):
        await plans.delete_by_id(item.id)


@pytest.mark.smoke
async def test_manual_add_creates_a_draft_position(async_test_session):
    await _clear(async_test_session)
    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): CellState(
                percent=Decimal("30"),
                is_done=False,
                work_cell_contractor_id=UUID("cccc0000-0000-0000-0000-000000000001"),
            )
        },
    )

    item, error = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)

    assert error is None
    assert item is not None
    assert item.source == "manual"
    assert item.status == PlanStatus.DRAFT
    # The cell percent is captured even for a hand-added position.
    assert item.source_percent == Decimal("30.00")
    assert item.work_cell_contractor_id == UUID("cccc0000-0000-0000-0000-000000000001")


async def test_manual_add_refuses_an_unassigned_contractor(async_test_session):
    """Spec: without an assignment the position would be undeliverable."""
    await _clear(async_test_session)
    service = _service(async_test_session, allowed_contractors=[CONTRACTOR_2])

    item, error = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)

    assert item is None
    assert error is not None
    assert "Не назначен подрядчик для работы" in error
    assert "Добавьте назначение в системе Рапорт" in error


async def test_manual_add_checks_the_floor_belongs_to_the_section(async_test_session):
    await _clear(async_test_session)
    service = _service(async_test_session)

    item, error = await service.add_manual_item(HOUSING, SECTION_2, FLOOR_1, WORK_A, CONTRACTOR, TARGET)

    assert item is None
    assert error == "Этаж не найден в этой секции."


async def test_manual_add_works_without_a_known_cell(async_test_session):
    """The spec allows stepping outside the sequence, so a cell may not exist yet."""
    await _clear(async_test_session)
    service = _service(async_test_session, cells={})

    item, error = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)

    assert error is None
    assert item is not None
    assert item.source_percent is None


async def test_confirm_moves_draft_to_confirmed(async_test_session):
    await _clear(async_test_session)
    service = _service(async_test_session)
    item, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)

    confirmed = await service.confirm_item(item.id)

    assert confirmed.status == PlanStatus.CONFIRMED
    assert confirmed.rs_confirmed is True


async def test_delete_removes_the_position(async_test_session):
    await _clear(async_test_session)
    service = _service(async_test_session)
    item, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)

    assert await service.delete_item(item.id) is True
    assert await service.delete_item(item.id) is False


async def test_transfer_moves_draft_and_confirmed_alike(async_test_session):
    """Spec: after the cutoff everything not deleted goes over, confirmed or not."""
    await _clear(async_test_session)
    service = _service(async_test_session)
    draft, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)
    other, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_2, WORK_A, CONTRACTOR, TARGET)
    await service.confirm_item(other.id)

    result = await service.transfer_day(TARGET, housing_id=HOUSING)

    assert result == {"transferred": 2}
    items = await service.plan_item_manager.search(housing_id=HOUSING, date=TARGET)
    assert {i.status for i in items} == {PlanStatus.TRANSFERRED}


async def test_transfer_is_idempotent(async_test_session):
    await _clear(async_test_session)
    service = _service(async_test_session)
    await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)

    first = await service.transfer_day(TARGET, housing_id=HOUSING)
    second = await service.transfer_day(TARGET, housing_id=HOUSING)

    assert first == {"transferred": 1}
    assert second == {"transferred": 0}


async def test_available_contractors_reads_the_assignment(async_test_session):
    service = _service(async_test_session, allowed_contractors=[CONTRACTOR])

    rows = await service.available_contractors(work_id=WORK_A, floor_id=FLOOR_1)

    assert [r["id"] for r in rows] == [CONTRACTOR]
    assert rows[0]["name"]


async def test_available_works_returns_the_four_level_tree(async_test_session):
    """The dropdown needs «Этап → Комплекс → Вид → Работа», scoped to the plan."""
    sequence = managers.TechSequenceItemManager(async_test_session)
    for existing in await sequence.search(housing_id=HOUSING):
        await sequence.delete_by_id(existing.id)
    await sequence.create(
        {
            "housing_id": HOUSING,
            "work_id": WORK_A,
            "order": 1,
            "depends_on": [],
            "depends_on_ss": [],
            "lag_days": 0,
            "estimated_days": 1,
            "daily_norm_volume": 0,
            "total_volume": 0,
            "source": "raport",
        }
    )
    service = _service(async_test_session)

    rows = await service.available_works(HOUSING, SECTION_1, FLOOR_1)

    assert len(rows) == 1
    row = rows[0]
    assert row["work"]["id"] == WORK_A
    assert row["work_type"]["id"] == WORK_TYPE
    # work_group / work_set are empty until the catalogue sync fills the upper levels.
    assert "work_group" in row and "work_set" in row


WORK_A_RAPORT = "60000000-0000-0000-0000-000000000001"
WORK_B = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORK_B_RAPORT = "60000000-0000-0000-0000-000000000002"


async def _sequence_of(session, *work_ids: UUID) -> None:
    """Put the given works into the housing-wide technological sequence."""
    sequence = managers.TechSequenceItemManager(session)
    for existing in await sequence.search(housing_id=HOUSING):
        await sequence.delete_by_id(existing.id)
    for order, work_id in enumerate(work_ids, start=1):
        await sequence.create(
            {
                "housing_id": HOUSING,
                "work_id": work_id,
                "order": order,
                "depends_on": [],
                "depends_on_ss": [],
                "lag_days": 0,
                "estimated_days": 1,
                "daily_norm_volume": 0,
                "total_volume": 0,
                "source": "raport",
            }
        )


async def test_the_dropdown_is_narrowed_to_the_floor(async_test_session):
    """Only works that Raport's chessboard has on that floor are offered."""
    await _sequence_of(async_test_session, WORK_A, WORK_B)
    service = _service(async_test_session, floor_works={WORK_A_RAPORT})

    rows = await service.available_works(HOUSING, SECTION_1, FLOOR_1)

    assert [row["work"]["id"] for row in rows] == [WORK_A]


async def test_a_floor_without_cells_offers_nothing(async_test_session):
    """An empty answer from Raport is an answer: this floor has no work to plan."""
    await _sequence_of(async_test_session, WORK_A, WORK_B)
    service = _service(async_test_session, floor_works=set())

    assert await service.available_works(HOUSING, SECTION_1, FLOOR_1) == []


async def test_an_unreachable_raport_offers_the_wider_list(async_test_session):
    """«Could not find out» must not look like «nothing can be done here»."""
    await _sequence_of(async_test_session, WORK_A, WORK_B)
    service = _service(async_test_session, floor_works=None)

    rows = await service.available_works(HOUSING, SECTION_1, FLOOR_1)

    assert {row["work"]["id"] for row in rows} == {WORK_A, WORK_B}


async def test_section_plan_narrows_the_dropdown(async_test_session):
    """A section with its own calendar plan offers only that plan's works."""
    sequence = managers.TechSequenceItemManager(async_test_session)
    for existing in await sequence.search(housing_id=HOUSING):
        await sequence.delete_by_id(existing.id)
    work_b = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    for work_id, section_id in ((WORK_A, None), (work_b, SECTION_1)):
        await sequence.create(
            {
                "housing_id": HOUSING,
                "section_id": section_id,
                "work_id": work_id,
                "order": 1,
                "depends_on": [],
                "depends_on_ss": [],
                "lag_days": 0,
                "estimated_days": 1,
                "daily_norm_volume": 0,
                "total_volume": 0,
                "source": "raport",
            }
        )
    service = _service(async_test_session)

    scoped = await service.available_works(HOUSING, SECTION_1, FLOOR_1)
    fallback = await service.available_works(HOUSING, SECTION_2, FLOOR_1)

    assert [r["work"]["id"] for r in scoped] == [work_b]
    assert [r["work"]["id"] for r in fallback] == [WORK_A]


async def test_journal_records_the_four_actions(async_test_session):
    """Spec: generation, manual add, delete and confirm all have to be traceable."""
    await _clear(async_test_session)
    logs = managers.ActionLogManager(async_test_session)
    for row in await logs.search():
        await logs.delete_by_id(row.id)

    service = _service(async_test_session)
    item, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)
    await service.confirm_item(item.id)
    await service.delete_item(item.id)
    await service.generate_daily_plan(HOUSING, TARGET, force=True)

    actions = {row.action for row in await logs.search()}
    assert actions == {
        ActionType.PLAN_ITEM_CREATE.value,
        ActionType.PLAN_ITEM_CONFIRM.value,
        ActionType.PLAN_ITEM_DELETE.value,
        ActionType.PLAN_GENERATE.value,
    }


async def test_bulk_confirm_handles_the_whole_selection(async_test_session):
    """A day holds ~136 positions; confirming them one by one is not a flow."""
    await _clear(async_test_session)
    service = _service(async_test_session)
    first, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)
    second, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_2, WORK_A, CONTRACTOR, TARGET)
    missing = UUID("00000000-0000-0000-0000-0000000000ff")

    result = await service.confirm_items([first.id, second.id, missing])

    assert result["confirmed"] == 2
    # An id that does not exist is reported, not silently dropped.
    assert result["not_found"] == [str(missing)]
    items = await service.plan_item_manager.search(housing_id=HOUSING, date=TARGET)
    assert {i.status for i in items} == {PlanStatus.CONFIRMED}


async def test_bulk_delete_removes_the_selection(async_test_session):
    await _clear(async_test_session)
    service = _service(async_test_session)
    first, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)
    second, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_2, WORK_A, CONTRACTOR, TARGET)

    result = await service.delete_items([first.id, second.id])

    assert result["deleted"] == 2
    assert await service.plan_item_manager.search(housing_id=HOUSING, date=TARGET) == []


async def test_bulk_operations_are_journalled_per_item(async_test_session):
    """The journal has to name every position, not just the batch."""
    await _clear(async_test_session)
    logs = managers.ActionLogManager(async_test_session)
    for row in await logs.search():
        await logs.delete_by_id(row.id)

    service = _service(async_test_session)
    first, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_1, WORK_A, CONTRACTOR, TARGET)
    second, _ = await service.add_manual_item(HOUSING, SECTION_1, FLOOR_2, WORK_A, CONTRACTOR, TARGET)
    await service.confirm_items([first.id, second.id])

    confirms = [r for r in await logs.search() if r.action == ActionType.PLAN_ITEM_CONFIRM.value]
    assert {r.entity_id for r in confirms} == {first.id, second.id}


class TestFloorLabels:
    """Raport is the master of the structure (DEV-6938): its floor names are shown
    verbatim — the dash pseudo-floor included. floor_number is a sort key, never a label."""

    def test_numeric_name_gets_the_prefix(self):
        from src.models.dbo.tables.housing import Floor
        from src.services.common import floor_label

        assert floor_label(Floor(name="3", floor_number=7)) == "Этаж 3"
        assert floor_label(Floor(name="-2", floor_number=1)) == "Этаж -2"

    def test_dash_is_shown_verbatim_not_renumbered(self):
        from src.models.dbo.tables.housing import Floor
        from src.services.common import floor_label

        assert floor_label(Floor(name="-", floor_number=1)) == "-"

    def test_a_real_name_wins(self):
        from src.models.dbo.tables.housing import Floor
        from src.services.common import floor_label

        assert floor_label(Floor(name="кровля", floor_number=25)) == "кровля"

    def test_empty_name_is_a_dash_not_a_number(self):
        from src.models.dbo.tables.housing import Floor
        from src.services.common import floor_label

        assert floor_label(Floor(name="  ", floor_number=4)) == "—"

    def test_no_floor_no_label(self):
        from src.services.common import floor_label

        assert floor_label(None) is None
