"""Plan-naryad generation over the technological graph, with Raport mocked out.

Fixtures give one housing with two sections; section 1 has floors 1 and 2. The tech
sequence is written per test so each graph shape is explicit.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.models import managers
from src.services.contractor_works import AssignmentKey, HousingAssignments
from src.services.plan.service import AutogenerationService, default_target_date
from src.services.report_cells import CellKey, CellState, HousingSlice

HOUSING = UUID("11111111-1111-1111-1111-111111111111")
SECTION_1 = UUID("33333333-3333-3333-3333-333333333333")
SECTION_2 = UUID("44444444-4444-4444-4444-444444444444")
FLOOR_1 = UUID("55555555-5555-5555-5555-555555555555")
FLOOR_2 = UUID("66666666-6666-6666-6666-666666666666")
WORK_A = UUID("88888888-8888-8888-8888-888888888888")
WORK_B = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CONTRACTOR = UUID("99999999-9999-9999-9999-999999999999")
CONTRACTOR_2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

TARGET = date(2026, 5, 20)


async def _sequence(session, rows: list[dict]) -> None:
    """Replace the housing's tech sequence with the given nodes."""
    manager = managers.TechSequenceItemManager(session)
    for existing in await manager.search(housing_id=HOUSING):
        await manager.delete_by_id(existing.id)
    for row in rows:
        await manager.create(
            {
                "housing_id": HOUSING,
                "section_id": row.get("section_id"),
                "work_id": row["work_id"],
                "order": row.get("order", 1),
                "depends_on": [str(d) for d in row.get("depends_on", [])],
                "depends_on_ss": [str(d) for d in row.get("depends_on_ss", [])],
                "lag_days": 0,
                "floor_sorting_direction": row.get("direction"),
                "estimated_days": 1,
                "daily_norm_volume": 0,
                "total_volume": 0,
                "source": "raport",
            }
        )


def _state(percent: str, wcc: str = "cccc0000-0000-0000-0000-000000000001") -> CellState:
    value = Decimal(percent)
    return CellState(percent=value, is_done=value >= 100, work_cell_contractor_id=UUID(wcc))


def _service(session, cells: dict, assignments: dict, skipped: dict | None = None) -> AutogenerationService:
    """Service with both Raport-backed collaborators replaced by fixed data."""
    service = AutogenerationService(session)
    service.report_cells = MagicMock()
    service.report_cells.get_housing_slice = AsyncMock(return_value=HousingSlice(cells=cells, skipped=skipped or {}))
    service.contractor_works = MagicMock()
    service.contractor_works.get_housing_assignments = AsyncMock(
        return_value=HousingAssignments(by_cell=assignments, skipped={})
    )
    return service


def _assign(*keys: AssignmentKey, contractor: UUID = CONTRACTOR) -> dict:
    return {key: [contractor] for key in keys}


async def _clear_plan(session) -> None:
    manager = managers.PlanItemManager(session)
    for item in await manager.search(housing_id=HOUSING, date=TARGET):
        await manager.delete_by_id(item.id)


@pytest.mark.smoke
async def test_root_work_is_planned_on_every_free_floor(async_test_session):
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])

    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0"),
            CellKey(SECTION_1, FLOOR_2, WORK_A, CONTRACTOR): _state("40"),
        },
        assignments=_assign(
            AssignmentKey(SECTION_1, FLOOR_1, WORK_A),
            AssignmentKey(SECTION_1, FLOOR_2, WORK_A),
        ),
    )

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET)

    assert reasons == []
    assert {(i.section_id, i.floor_id, i.work_id) for i in items} == {
        (SECTION_1, FLOOR_1, WORK_A),
        (SECTION_1, FLOOR_2, WORK_A),
    }
    # The percent at generation time is snapshotted for the «% Исходный» column.
    by_floor = {i.floor_id: i for i in items}
    assert by_floor[FLOOR_2].source_percent == Decimal("40.00")


async def test_finished_cell_is_not_planned_again(async_test_session):
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])

    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("100"),
            CellKey(SECTION_1, FLOOR_2, WORK_A, CONTRACTOR): _state("10"),
        },
        assignments=_assign(
            AssignmentKey(SECTION_1, FLOOR_1, WORK_A),
            AssignmentKey(SECTION_1, FLOOR_2, WORK_A),
        ),
    )

    items, _ = await service.generate_daily_plan(HOUSING, TARGET)

    assert [i.floor_id for i in items] == [FLOOR_2]


async def test_successor_waits_for_its_predecessor(async_test_session):
    """B depends on A; on the floor where A is unfinished, B must not appear."""
    await _clear_plan(async_test_session)
    await _sequence(
        async_test_session,
        [
            {"work_id": WORK_A, "order": 1},
            {"work_id": WORK_B, "order": 2, "depends_on": [WORK_A]},
        ],
    )

    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("100"),
            CellKey(SECTION_1, FLOOR_1, WORK_B, CONTRACTOR): _state("0"),
            CellKey(SECTION_1, FLOOR_2, WORK_A, CONTRACTOR): _state("50"),
            CellKey(SECTION_1, FLOOR_2, WORK_B, CONTRACTOR): _state("0"),
        },
        assignments=_assign(
            AssignmentKey(SECTION_1, FLOOR_1, WORK_B),
            AssignmentKey(SECTION_1, FLOOR_2, WORK_A),
        ),
    )

    items, _ = await service.generate_daily_plan(HOUSING, TARGET)

    planned = {(i.floor_id, i.work_id) for i in items}
    assert planned == {(FLOOR_1, WORK_B), (FLOOR_2, WORK_A)}


async def test_work_with_several_predecessors_needs_all_of_them(async_test_session):
    """The graph is not a chain: B waits for A **and** the second predecessor."""
    await _clear_plan(async_test_session)
    work_c = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    works = managers.WorkManager(async_test_session)
    if not await works.get_by_id(work_c):
        await works.create(
            {
                "id": work_c,
                "work_type_id": UUID("77777777-7777-7777-7777-777777777777"),
                "name": "Третья работа",
                "code": "THIRD",
                "unit": "шт",
            }
        )
    await _sequence(
        async_test_session,
        [
            {"work_id": WORK_A, "order": 1},
            {"work_id": work_c, "order": 2},
            {"work_id": WORK_B, "order": 3, "depends_on": [WORK_A, work_c]},
        ],
    )

    # A is finished, C is not → B stays blocked even though one predecessor is done.
    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("100"),
            CellKey(SECTION_1, FLOOR_1, work_c, CONTRACTOR): _state("60"),
            CellKey(SECTION_1, FLOOR_1, WORK_B, CONTRACTOR): _state("0"),
        },
        assignments=_assign(
            AssignmentKey(SECTION_1, FLOOR_1, work_c),
            AssignmentKey(SECTION_1, FLOOR_1, WORK_B),
        ),
    )

    items, _ = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert {i.work_id for i in items} == {work_c}


async def test_start_to_start_predecessor_only_needs_a_start(async_test_session):
    """SS edges gate on «has started», not on «is finished» — 11k such edges exist."""
    await _clear_plan(async_test_session)
    await _sequence(
        async_test_session,
        [
            {"work_id": WORK_A, "order": 1},
            {"work_id": WORK_B, "order": 2, "depends_on_ss": [WORK_A]},
        ],
    )

    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("15"),
            CellKey(SECTION_1, FLOOR_1, WORK_B, CONTRACTOR): _state("0"),
        },
        assignments=_assign(AssignmentKey(SECTION_1, FLOOR_1, WORK_B)),
    )

    items, _ = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert WORK_B in {i.work_id for i in items}


async def test_start_to_start_predecessor_not_started_blocks(async_test_session):
    await _clear_plan(async_test_session)
    await _sequence(
        async_test_session,
        [
            {"work_id": WORK_A, "order": 1},
            {"work_id": WORK_B, "order": 2, "depends_on_ss": [WORK_A]},
        ],
    )

    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0"),
            CellKey(SECTION_1, FLOOR_1, WORK_B, CONTRACTOR): _state("0"),
        },
        assignments=_assign(AssignmentKey(SECTION_1, FLOOR_1, WORK_B)),
    )

    items, _ = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert WORK_B not in {i.work_id for i in items}


async def test_section_plan_overrides_the_housing_one(async_test_session):
    """A section with its own calendar plan is generated from it alone."""
    await _clear_plan(async_test_session)
    await _sequence(
        async_test_session,
        [
            {"work_id": WORK_A, "order": 1},  # housing-wide
            {"work_id": WORK_B, "order": 1, "section_id": SECTION_1},  # section 1 only
        ],
    )

    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0"),
            CellKey(SECTION_1, FLOOR_1, WORK_B, CONTRACTOR): _state("0"),
        },
        assignments=_assign(
            AssignmentKey(SECTION_1, FLOOR_1, WORK_A),
            AssignmentKey(SECTION_1, FLOOR_1, WORK_B),
        ),
    )

    items, _ = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert {i.work_id for i in items} == {WORK_B}


async def test_floor_limit_caps_one_contractor(async_test_session):
    """Default limit is 4 floors of one work per contractor (Р8)."""
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])

    floors = managers.FloorManager(async_test_session)
    extra_ids = []
    for number in range(3, 8):
        rows = await floors.search(section_id=SECTION_1, floor_number=number)
        row = (
            rows[0]
            if rows
            else await floors.create({"section_id": SECTION_1, "floor_number": number, "name": f"Этаж {number}"})
        )
        extra_ids.append(row.id)

    all_floors = [FLOOR_1, FLOOR_2, *extra_ids]
    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, f, WORK_A, CONTRACTOR): _state("0") for f in all_floors},
        assignments=_assign(*[AssignmentKey(SECTION_1, f, WORK_A) for f in all_floors]),
    )

    items, _ = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert len(items) == 4


async def test_missing_assignment_reports_the_spec_wording(async_test_session):
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])

    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0")},
        assignments={},
    )

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert items == []
    assert any("Не назначен подрядчик для работы" in r for r in reasons)
    assert any("Добавьте назначение в системе Рапорт" in r for r in reasons)


async def test_ambiguous_assignment_is_not_guessed(async_test_session):
    """Two contractors on one cell — the generator refuses rather than picking one."""
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])

    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0")},
        assignments={AssignmentKey(SECTION_1, FLOOR_1, WORK_A): [CONTRACTOR, CONTRACTOR_2]},
    )

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert items == []
    assert any("Не назначен подрядчик" in r for r in reasons)


async def test_no_calendar_plan_reports_the_spec_wording(async_test_session):
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [])

    service = _service(async_test_session, cells={}, assignments={})

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET)

    assert items == []
    assert any("не сформирован календарный план" in r for r in reasons)


async def test_rerun_without_force_keeps_existing_items(async_test_session):
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])
    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0")},
        assignments=_assign(AssignmentKey(SECTION_1, FLOOR_1, WORK_A)),
    )
    first, _ = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)
    assert len(first) == 1

    again, _ = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert {i.id for i in again} == {i.id for i in first}


async def test_rerun_with_force_rebuilds_the_day(async_test_session):
    """`force` wipes the day, manual positions included, and generates anew."""
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])
    plans = managers.PlanItemManager(async_test_session)
    manual = await plans.create(
        {
            "date": TARGET,
            "housing_id": HOUSING,
            "section_id": SECTION_1,
            "floor_id": FLOOR_2,
            "work_id": WORK_B,
            "contractor_id": CONTRACTOR,
            "source": "manual",
            "status": "draft",
        }
    )

    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0")},
        assignments=_assign(AssignmentKey(SECTION_1, FLOOR_1, WORK_A)),
    )

    items, _ = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1, force=True)

    ids = {i.id for i in items}
    assert manual.id not in ids
    assert {i.work_id for i in items} == {WORK_A}


async def _manual_item(session):
    return await managers.PlanItemManager(session).create(
        {
            "date": TARGET,
            "housing_id": HOUSING,
            "section_id": SECTION_1,
            "floor_id": FLOOR_2,
            "work_id": WORK_B,
            "contractor_id": CONTRACTOR,
            "source": "manual",
            "status": "draft",
        }
    )


async def test_an_empty_chessboard_keeps_the_existing_day(async_test_session):
    """An outage looks like «no cells»; «replace the day» must not turn it into a lost day."""
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])
    manual = await _manual_item(async_test_session)

    service = _service(async_test_session, cells={}, assignments={})

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET, force=True)

    assert items == []
    assert any("оставлен без изменений" in r for r in reasons)
    kept = await managers.PlanItemManager(async_test_session).search(housing_id=HOUSING, date=TARGET)
    assert [i.id for i in kept] == [manual.id]


async def test_no_calendar_plan_keeps_the_existing_day(async_test_session):
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [])
    manual = await _manual_item(async_test_session)

    service = _service(async_test_session, cells={}, assignments={})

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET, force=True)

    assert items == []
    assert any("календарный план" in r for r in reasons)
    kept = await managers.PlanItemManager(async_test_session).search(housing_id=HOUSING, date=TARGET)
    assert [i.id for i in kept] == [manual.id]


async def test_a_day_with_no_ready_work_is_still_replaced(async_test_session):
    """Raport answered — every cell is finished — so the spec's «replace the day» applies."""
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])
    await _manual_item(async_test_session)

    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("100")},
        assignments=_assign(AssignmentKey(SECTION_1, FLOOR_1, WORK_A)),
    )

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET, force=True)

    assert items == []
    assert reasons and not any("оставлен без изменений" in r for r in reasons)
    assert await managers.PlanItemManager(async_test_session).search(housing_id=HOUSING, date=TARGET) == []


async def test_skipped_cells_surface_in_reasons(async_test_session):
    """An unsynced entity must be visible, not quietly thin the plan out."""
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])

    service = _service(async_test_session, cells={}, assignments={}, skipped={"floor_not_synced": 3})

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET, section_id=SECTION_1)

    assert items == []
    assert any("floor_not_synced=3" in r for r in reasons)


def test_default_target_date_follows_the_cutoff():
    """Night run targets today; a daytime run targets tomorrow (Р3)."""
    assert default_target_date(datetime(2026, 5, 20, 3, 0)) == date(2026, 5, 20)
    assert default_target_date(datetime(2026, 5, 20, 15, 0)) == date(2026, 5, 21)


async def test_work_without_a_cell_is_not_planned_there(async_test_session):
    """DEV-6858 item 9: a КП covering one section must not spill onto the others.

    A root work (no predecessors) used to be «ready» on every section and floor,
    including cells Raport does not have at all — the positions were undeliverable.
    """
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])

    service = _service(
        async_test_session,
        # The chessboard knows the work only on section 1, floor 1.
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0")},
        assignments=_assign(
            AssignmentKey(SECTION_1, FLOOR_1, WORK_A),
            AssignmentKey(SECTION_1, FLOOR_2, WORK_A),
            AssignmentKey(SECTION_2, FLOOR_1, WORK_A),
        ),
    )

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET)

    assert reasons == []
    assert {(i.section_id, i.floor_id) for i in items} == {(SECTION_1, FLOOR_1)}


async def test_partial_generation_still_reports_missing_contractors(async_test_session):
    """DEV-6858 item 13: a skipped position must be explained even when others made it."""
    await _clear_plan(async_test_session)
    await _sequence(async_test_session, [{"work_id": WORK_A, "order": 1}])

    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0"),
            CellKey(SECTION_1, FLOOR_2, WORK_A, CONTRACTOR): _state("0"),
        },
        # Floor 2 has the cell but nobody assigned.
        assignments=_assign(AssignmentKey(SECTION_1, FLOOR_1, WORK_A)),
    )

    items, reasons = await service.generate_daily_plan(HOUSING, TARGET)

    assert {(i.floor_id) for i in items} == {FLOOR_1}
    assert any("Не назначен подрядчик" in r for r in reasons)
