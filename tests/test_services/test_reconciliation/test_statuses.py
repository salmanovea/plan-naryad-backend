"""Reconciliation statuses on percent growth (decision Р6c).

The old rule divided fact volume by planned volume; the spec removed the volume field from a
position, so status now follows «% Исходный» → «% Факт» on the chessboard cell.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.models import managers
from src.models.dbo.tables.reconciliation import ReconciliationStatus
from src.services.reconciliation.service import ReconciliationService
from src.services.report_cells import CellKey, CellState, HousingSlice

HOUSING = UUID("11111111-1111-1111-1111-111111111111")
SECTION_1 = UUID("33333333-3333-3333-3333-333333333333")
FLOOR_1 = UUID("55555555-5555-5555-5555-555555555555")
FLOOR_2 = UUID("66666666-6666-6666-6666-666666666666")
WORK_A = UUID("88888888-8888-8888-8888-888888888888")
CONTRACTOR = UUID("99999999-9999-9999-9999-999999999999")

DAY = date(2026, 9, 1)


def _classify(source: str | None, fact: str | None, has_plan: bool = True, has_fact: bool = True):
    return ReconciliationService.classify_status(
        Decimal(source) if source is not None else None,
        Decimal(fact) if fact is not None else None,
        has_plan,
        has_fact,
    )


# ── The table from Р6c, one case per row ──────────────────────────────────────


@pytest.mark.smoke
def test_hundred_percent_is_done_full():
    status, ratio = _classify("40", "100")
    assert status is ReconciliationStatus.DONE_FULL
    assert ratio == Decimal("1.0000")


def test_growth_below_hundred_is_done_partial():
    """«прирост > 0, но % Факт < 100» — the contractor worked but did not finish."""
    status, ratio = _classify("40", "65")
    assert status is ReconciliationStatus.DONE_PARTIAL
    assert ratio == Decimal("0.6500")


def test_no_growth_with_facts_is_not_done():
    status, _ = _classify("40", "40")
    assert status is ReconciliationStatus.NOT_DONE


def test_percent_going_backwards_is_not_done():
    """A correction in Raport can lower the percent; that is still «не выполнено»."""
    status, _ = _classify("40", "30")
    assert status is ReconciliationStatus.NOT_DONE


def test_absent_facts_are_no_report():
    status, ratio = _classify("40", None, has_fact=False)
    assert status is ReconciliationStatus.NO_REPORT
    assert ratio == Decimal("0")


def test_fact_without_a_plan_is_unplanned():
    status, _ = _classify(None, "70", has_plan=False)
    assert status is ReconciliationStatus.UNPLANNED


def test_growth_from_zero_is_partial_not_full():
    status, _ = _classify("0", "5")
    assert status is ReconciliationStatus.DONE_PARTIAL


def test_done_over_is_never_produced():
    """Raport clamps the percent at 100, so overachievement is unrepresentable."""
    for source, fact in (("0", "100"), ("50", "100"), ("100", "100")):
        status, _ = _classify(source, fact)
        assert status is not ReconciliationStatus.DONE_OVER


# ── Full runs over a range ────────────────────────────────────────────────────


def _service(session, cells: dict) -> ReconciliationService:
    service = ReconciliationService(session)
    service.report_cells = MagicMock()
    service.report_cells.get_housing_slice = AsyncMock(return_value=HousingSlice(cells=cells))
    return service


def _state(percent: str) -> CellState:
    value = Decimal(percent)
    return CellState(
        percent=value,
        is_done=value >= 100,
        work_cell_contractor_id=UUID("cccc0000-0000-0000-0000-0000000000aa"),
    )


async def _plan(session, day: date, *, source_percent: str | None = None, floor_id: UUID = FLOOR_1):
    return await managers.PlanItemManager(session).create(
        {
            "date": day,
            "housing_id": HOUSING,
            "section_id": SECTION_1,
            "floor_id": floor_id,
            "work_id": WORK_A,
            "contractor_id": CONTRACTOR,
            "source_percent": source_percent,
            "source": "auto",
            "status": "transferred",
        }
    )


async def _fact(session, day: date, raport_id: str, *, floor_id: UUID = FLOOR_1, contractor=CONTRACTOR):
    return await managers.WorkFactManager(session).create(
        {
            "raport_id": raport_id,
            "work_date": day,
            "housing_id": HOUSING,
            "section_id": SECTION_1,
            "floor_id": floor_id,
            "work_id": WORK_A,
            "contractor_id": contractor,
            "volume": 0,
            "percent": "50",
            "source": "raport",
        }
    )


async def _clear(session, days: list[date]) -> None:
    for manager, field in (
        (managers.ReconciliationResultManager(session), "date"),
        (managers.DailySummaryManager(session), "date"),
        (managers.PlanItemManager(session), "date"),
    ):
        for day in days:
            for row in await manager.search(**{field: day, "housing_id": HOUSING}):
                await manager.delete_by_id(row.id)
    facts = managers.WorkFactManager(session)
    for day in days:
        for row in await facts.search(work_date=day, housing_id=HOUSING):
            await facts.delete_by_id(row.id)


@pytest.mark.smoke
async def test_run_uses_the_chessboard_percent(async_test_session):
    await _clear(async_test_session, [DAY])
    await _plan(async_test_session, DAY, source_percent="20")
    await _fact(async_test_session, DAY, "dddd0000-0000-0000-0000-000000000001")
    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("80")},
    )

    result = await service.run_reconciliation(DAY, housing_id=HOUSING)

    assert result["total_results"] == 1
    rows = await managers.ReconciliationResultManager(async_test_session).search(date=DAY, housing_id=HOUSING)
    row = rows[0]
    assert row.source_percent == Decimal("20.00")
    assert row.fact_percent == Decimal("80.00")
    assert row.status == ReconciliationStatus.DONE_PARTIAL


async def test_run_walks_every_day_of_the_range(async_test_session):
    """The screen asks for a range; each day gets its own rows and summary."""
    days = [DAY, DAY + timedelta(days=1), DAY + timedelta(days=2)]
    await _clear(async_test_session, days)
    for offset, day in enumerate(days):
        await _plan(async_test_session, day, source_percent="0")
        await _fact(async_test_session, day, f"dddd0000-0000-0000-0000-00000000010{offset}")
    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("100")},
    )

    result = await service.run_reconciliation(days[0], days[-1], housing_id=HOUSING)

    assert result["total_results"] == 3
    assert result["total_summaries"] == 3
    assert result["date_from"] == days[0]
    assert result["date_to"] == days[-1]
    for day in days:
        rows = await managers.ReconciliationResultManager(async_test_session).search(date=day, housing_id=HOUSING)
        assert [r.status for r in rows] == [ReconciliationStatus.DONE_FULL]


async def test_reversed_range_is_accepted(async_test_session):
    """Swapped dates are a UI slip, not a reason to return nothing."""
    days = [DAY, DAY + timedelta(days=1)]
    await _clear(async_test_session, days)
    await _plan(async_test_session, DAY, source_percent="0")
    service = _service(async_test_session, cells={})

    result = await service.run_reconciliation(days[1], days[0], housing_id=HOUSING)

    assert result["date_from"] == days[0]
    assert result["date_to"] == days[1]


async def test_rerun_replaces_instead_of_duplicating(async_test_session):
    await _clear(async_test_session, [DAY])
    await _plan(async_test_session, DAY, source_percent="10")
    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("55")},
    )

    first = await service.run_reconciliation(DAY, housing_id=HOUSING)
    second = await service.run_reconciliation(DAY, housing_id=HOUSING)

    assert first["total_results"] == second["total_results"] == 1
    rows = await managers.ReconciliationResultManager(async_test_session).search(date=DAY, housing_id=HOUSING)
    assert len(rows) == 1


async def test_unattributed_fact_becomes_an_unplanned_row(async_test_session):
    """Raport rarely names the contractor; such a fact still has to show up (Р6)."""
    await _clear(async_test_session, [DAY])
    await _fact(async_test_session, DAY, "dddd0000-0000-0000-0000-000000000201", contractor=None)
    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("35")},
    )

    await service.run_reconciliation(DAY, housing_id=HOUSING)

    rows = await managers.ReconciliationResultManager(async_test_session).search(date=DAY, housing_id=HOUSING)
    assert len(rows) == 1
    assert rows[0].status == ReconciliationStatus.UNPLANNED
    assert rows[0].contractor_id is None
    # The percent still comes through — taken from whoever holds the cell.
    assert rows[0].fact_percent == Decimal("35.00")


async def test_planned_cell_without_facts_is_no_report(async_test_session):
    await _clear(async_test_session, [DAY])
    await _plan(async_test_session, DAY, source_percent="0")
    service = _service(
        async_test_session,
        cells={CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("0")},
    )

    await service.run_reconciliation(DAY, housing_id=HOUSING)

    rows = await managers.ReconciliationResultManager(async_test_session).search(date=DAY, housing_id=HOUSING)
    assert [r.status for r in rows] == [ReconciliationStatus.NO_REPORT]


async def test_summary_counts_and_rates(async_test_session):
    """Summary keeps counters; `weighted_completion` is now the mean cell percent."""
    await _clear(async_test_session, [DAY])
    await _plan(async_test_session, DAY, source_percent="0", floor_id=FLOOR_1)
    await _plan(async_test_session, DAY, source_percent="0", floor_id=FLOOR_2)
    await _fact(async_test_session, DAY, "dddd0000-0000-0000-0000-000000000301", floor_id=FLOOR_1)
    await _fact(async_test_session, DAY, "dddd0000-0000-0000-0000-000000000302", floor_id=FLOOR_2)
    service = _service(
        async_test_session,
        cells={
            CellKey(SECTION_1, FLOOR_1, WORK_A, CONTRACTOR): _state("100"),
            CellKey(SECTION_1, FLOOR_2, WORK_A, CONTRACTOR): _state("50"),
        },
    )

    await service.run_reconciliation(DAY, housing_id=HOUSING)

    summaries = await managers.DailySummaryManager(async_test_session).search(date=DAY, housing_id=HOUSING)
    summary = summaries[0]
    assert summary.total_planned == 2
    assert summary.total_done_full == 1
    assert summary.total_done_partial == 1
    assert summary.total_done_over == 0
    # One of two planned rows finished → 0.5; mean percent (100 + 50) / 200 → 0.75.
    assert summary.completion_rate == Decimal("0.5000")
    assert summary.weighted_completion == Decimal("0.7500")
