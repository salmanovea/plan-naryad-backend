"""Plan/fact matching, deviation patterns and the per-contractor summary.

One row per plan item; facts of a key are grouped and only facts with progress count as a
report. Patterns: WRONG_LOCATION / WRONG_WORK_TYPE on unplanned rows, CHRONIC_NO_REPORT on
a position left without a report on three of its contractor's plan days in a row.
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.models import managers
from src.models.dbo.tables.reconciliation import ReconciliationPattern, ReconciliationStatus
from src.services.reconciliation.service import ReconciliationService
from src.services.report_cells import HousingSlice

HOUSING = UUID("11111111-1111-1111-1111-111111111111")
HOUSING_RAPORT_ID = "10000000-0000-0000-0000-000000000001"
SECTION_1 = UUID("33333333-3333-3333-3333-333333333333")
FLOOR_1 = UUID("55555555-5555-5555-5555-555555555555")
FLOOR_2 = UUID("66666666-6666-6666-6666-666666666666")
WORK_A = UUID("88888888-8888-8888-8888-888888888888")
WORK_B = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CONTRACTOR_1 = UUID("99999999-9999-9999-9999-999999999999")
CONTRACTOR_2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

START = date(2027, 3, 1)
SPAN_END = START + timedelta(days=30)


async def _wipe(session) -> None:
    """Drop this module's plans and facts, and every reconciliation row of the housing.

    Results are derived data, and the chronic pattern reads the days before a run — rows left
    by other modules would leak into that history.
    """
    for manager in (managers.ReconciliationResultManager(session), managers.DailySummaryManager(session)):
        await manager.bulk_delete([r.id for r in await manager.search(housing_id=HOUSING)])
    plans = managers.PlanItemManager(session)
    await plans.bulk_delete([p.id for p in await plans.search(housing_id=HOUSING, date__gte=START, date__lte=SPAN_END)])
    facts = managers.WorkFactManager(session)
    await facts.bulk_delete(
        [f.id for f in await facts.search(housing_id=HOUSING, work_date__gte=START, work_date__lte=SPAN_END)]
    )
    await session.commit()


@pytest.fixture(autouse=True)
async def _clean(async_test_session):
    await _wipe(async_test_session)
    yield
    await _wipe(async_test_session)


def _service(session, *, sync_result: dict | None = None) -> ReconciliationService:
    service = ReconciliationService(session)
    service.report_cells = MagicMock()
    service.report_cells.get_housing_slice = AsyncMock(return_value=HousingSlice())
    service.sync = MagicMock()
    service.sync.sync_work_facts = AsyncMock(
        return_value=sync_result or {"work_facts": 0, "removed": 0, "complete": True}
    )
    return service


async def _plan(session, day: date, *, floor=FLOOR_1, work=WORK_A, contractor=CONTRACTOR_1):
    return await managers.PlanItemManager(session).create(
        {
            "date": day,
            "housing_id": HOUSING,
            "section_id": SECTION_1,
            "floor_id": floor,
            "work_id": work,
            "contractor_id": contractor,
            "source_percent": "0",
            "source": "auto",
            "status": "transferred",
        }
    )


async def _fact(
    session,
    day: date,
    *,
    floor=FLOOR_1,
    work=WORK_A,
    contractor=CONTRACTOR_1,
    percent: str | None = "40",
    volume: str = "0",
    submitted_at: datetime | None = None,
):
    return await managers.WorkFactManager(session).create(
        {
            "raport_id": f"match-{uuid4()}",
            "work_date": day,
            "housing_id": HOUSING,
            "section_id": SECTION_1,
            "floor_id": floor,
            "work_id": work,
            "contractor_id": contractor,
            "volume": volume,
            "percent": percent,
            "submitted_at": submitted_at or datetime.combine(day, datetime.min.time()).replace(hour=12),
            "source": "raport",
        }
    )


async def _run(session, date_from: date, date_to: date | None = None, **service_kwargs) -> dict:
    return await _service(session, **service_kwargs).run_reconciliation(date_from, date_to, housing_id=HOUSING)


async def _rows(session, day: date) -> list:
    return await managers.ReconciliationResultManager(session).search(date=day, housing_id=HOUSING)


def _by_place(rows: list) -> dict:
    return {(r.contractor_id, r.floor_id, r.work_id): r for r in rows}


# ── What counts as a report ───────────────────────────────────────────────────


@pytest.mark.smoke
async def test_zero_percent_fact_is_not_a_report(async_test_session):
    await _plan(async_test_session, START)
    await _fact(async_test_session, START, percent="0")

    await _run(async_test_session, START)

    [row] = await _rows(async_test_session, START)
    assert row.status == ReconciliationStatus.NO_REPORT
    assert row.work_fact_id is None


async def test_zero_percent_fact_outside_the_plan_makes_no_row(async_test_session):
    await _fact(async_test_session, START, percent="0")

    result = await _run(async_test_session, START)

    assert result["total_results"] == 0


@pytest.mark.parametrize(("volume", "reported"), [("5", True), ("0", False)])
async def test_volume_decides_for_a_fact_without_percent(async_test_session, volume, reported):
    await _plan(async_test_session, START)
    await _fact(async_test_session, START, percent=None, volume=volume)

    await _run(async_test_session, START)

    [row] = await _rows(async_test_session, START)
    assert (row.status != ReconciliationStatus.NO_REPORT) is reported


# ── Grouping ──────────────────────────────────────────────────────────────────


async def test_facts_of_one_key_make_one_row_linked_to_the_latest(async_test_session):
    await _plan(async_test_session, START)
    noon = datetime.combine(START, datetime.min.time()).replace(hour=12)
    await _fact(async_test_session, START, submitted_at=noon)
    latest = await _fact(async_test_session, START, submitted_at=noon + timedelta(hours=9))

    await _run(async_test_session, START)

    [row] = await _rows(async_test_session, START)
    assert row.status != ReconciliationStatus.NO_REPORT
    assert row.work_fact_id == latest.id


async def test_every_plan_item_is_a_row_of_its_own(async_test_session):
    """A duplicated position is not folded into one row — the issued count must stay whole."""
    first = await _plan(async_test_session, START)
    second = await _plan(async_test_session, START)
    await _fact(async_test_session, START)

    result = await _run(async_test_session, START)

    rows = await _rows(async_test_session, START)
    assert result["total_results"] == 2
    assert {r.plan_item_id for r in rows} == {first.id, second.id}
    assert all(r.status != ReconciliationStatus.NO_REPORT for r in rows)


# ── WRONG_LOCATION / WRONG_WORK_TYPE ──────────────────────────────────────────


@pytest.mark.smoke
async def test_planned_work_done_on_another_floor_is_wrong_location(async_test_session):
    await _plan(async_test_session, START, floor=FLOOR_1)
    await _fact(async_test_session, START, floor=FLOOR_2)

    await _run(async_test_session, START)

    rows = _by_place(await _rows(async_test_session, START))
    planned = rows[(CONTRACTOR_1, FLOOR_1, WORK_A)]
    unplanned = rows[(CONTRACTOR_1, FLOOR_2, WORK_A)]
    assert (planned.status, planned.pattern) == (ReconciliationStatus.NO_REPORT, None)
    assert (unplanned.status, unplanned.pattern) == (
        ReconciliationStatus.UNPLANNED,
        ReconciliationPattern.WRONG_LOCATION,
    )


async def test_another_work_on_the_planned_floor_is_wrong_work_type(async_test_session):
    await _plan(async_test_session, START, work=WORK_A)
    await _fact(async_test_session, START, work=WORK_B)

    await _run(async_test_session, START)

    unplanned = _by_place(await _rows(async_test_session, START))[(CONTRACTOR_1, FLOOR_1, WORK_B)]
    assert unplanned.pattern == ReconciliationPattern.WRONG_WORK_TYPE


async def test_location_wins_when_both_patterns_apply(async_test_session):
    await _plan(async_test_session, START, floor=FLOOR_1, work=WORK_A)
    await _plan(async_test_session, START, floor=FLOOR_2, work=WORK_B)
    await _fact(async_test_session, START, floor=FLOOR_2, work=WORK_A)

    await _run(async_test_session, START)

    unplanned = _by_place(await _rows(async_test_session, START))[(CONTRACTOR_1, FLOOR_2, WORK_A)]
    assert unplanned.pattern == ReconciliationPattern.WRONG_LOCATION


async def test_extra_work_next_to_a_reported_position_has_no_pattern(async_test_session):
    await _plan(async_test_session, START, floor=FLOOR_1)
    await _fact(async_test_session, START, floor=FLOOR_1)
    await _fact(async_test_session, START, floor=FLOOR_2)

    await _run(async_test_session, START)

    unplanned = _by_place(await _rows(async_test_session, START))[(CONTRACTOR_1, FLOOR_2, WORK_A)]
    assert (unplanned.status, unplanned.pattern) == (ReconciliationStatus.UNPLANNED, None)


async def test_another_contractors_position_does_not_count(async_test_session):
    await _plan(async_test_session, START, floor=FLOOR_1, contractor=CONTRACTOR_1)
    await _fact(async_test_session, START, floor=FLOOR_2, contractor=CONTRACTOR_2)

    await _run(async_test_session, START)

    unplanned = _by_place(await _rows(async_test_session, START))[(CONTRACTOR_2, FLOOR_2, WORK_A)]
    assert unplanned.pattern is None


# ── CHRONIC_NO_REPORT ─────────────────────────────────────────────────────────


@pytest.mark.smoke
async def test_third_plan_day_without_report_is_chronic(async_test_session):
    """Days without positions (START+2) do not break the series."""
    days = [START, START + timedelta(days=1), START + timedelta(days=3)]
    for day in days:
        await _plan(async_test_session, day)

    await _run(async_test_session, days[0], days[-1])

    patterns = [(await _rows(async_test_session, day))[0].pattern for day in days]
    assert patterns == [None, None, ReconciliationPattern.CHRONIC_NO_REPORT]


async def test_plan_day_without_the_position_breaks_the_series(async_test_session):
    days = [START + timedelta(days=i) for i in range(3)]
    await _plan(async_test_session, days[0], floor=FLOOR_1)
    await _plan(async_test_session, days[1], floor=FLOOR_2)
    await _plan(async_test_session, days[2], floor=FLOOR_1)

    await _run(async_test_session, days[0], days[-1])

    [last] = await _rows(async_test_session, days[2])
    assert (last.status, last.pattern) == (ReconciliationStatus.NO_REPORT, None)


async def test_a_report_breaks_the_series(async_test_session):
    days = [START + timedelta(days=i) for i in range(3)]
    for day in days:
        await _plan(async_test_session, day)
    await _fact(async_test_session, days[1])

    await _run(async_test_session, days[0], days[-1])

    [last] = await _rows(async_test_session, days[2])
    assert last.pattern is None


async def test_series_continues_from_results_stored_earlier(async_test_session):
    days = [START + timedelta(days=i) for i in range(3)]
    for day in days:
        await _plan(async_test_session, day)

    await _run(async_test_session, days[0], days[1])
    await _run(async_test_session, days[2])

    [last] = await _rows(async_test_session, days[2])
    assert last.pattern == ReconciliationPattern.CHRONIC_NO_REPORT


async def test_series_is_kept_per_contractor(async_test_session):
    days = [START + timedelta(days=i) for i in range(3)]
    for day in days[:2]:
        await _plan(async_test_session, day, contractor=CONTRACTOR_1)
    await _plan(async_test_session, days[2], contractor=CONTRACTOR_2)

    await _run(async_test_session, days[0], days[-1])

    [last] = await _rows(async_test_session, days[2])
    assert last.pattern is None


# ── Facts are synced before the run ───────────────────────────────────────────


async def test_run_syncs_the_range_from_raport_first(async_test_session):
    service = _service(async_test_session, sync_result={"work_facts": 4, "removed": 1, "complete": True})

    result = await service.run_reconciliation(START, START + timedelta(days=2), housing_id=HOUSING)

    service.sync.sync_work_facts.assert_awaited_once_with(
        HOUSING_RAPORT_ID, date_from=START, date_to=START + timedelta(days=2)
    )
    assert (result["facts_synced"], result["facts_removed"], result["facts_sync_failed"]) == (4, 1, 0)


async def test_unreadable_raport_is_reported_and_the_run_goes_on(async_test_session):
    await _plan(async_test_session, START)

    result = await _run(async_test_session, START, sync_result={"work_facts": 0, "removed": 0, "complete": False})

    assert result["facts_sync_failed"] == 1
    assert result["total_results"] == 1


# ── «Сводка» per contractor ───────────────────────────────────────────────────


async def _seed_summary_day(session) -> None:
    """CONTRACTOR_1: two positions, one reported. CONTRACTOR_2: one unreported, one fact off-plan."""
    await _plan(session, START, floor=FLOOR_1, contractor=CONTRACTOR_1)
    await _fact(session, START, floor=FLOOR_1, contractor=CONTRACTOR_1)
    await _plan(session, START, floor=FLOOR_2, contractor=CONTRACTOR_1)
    await _plan(session, START, floor=FLOOR_1, work=WORK_B, contractor=CONTRACTOR_2)
    await _fact(session, START, floor=FLOOR_2, work=WORK_B, contractor=CONTRACTOR_2)
    await _run(session, START)


@pytest.mark.smoke
async def test_contractor_summary_counts_the_four_indicators(async_test_session):
    await _seed_summary_day(async_test_session)

    summary = await _service(async_test_session).contractor_summary(
        housing_id=HOUSING, date_from=START, date_to=START + timedelta(days=1)
    )

    rows = {item["contractor_name"]: item for item in summary["items"]}
    indicators = ("issued", "reported", "not_reported", "unplanned")
    assert [item["contractor_name"] for item in summary["items"]] == ["ИП Петров", "ООО Стройтест"]
    assert tuple(rows["ООО Стройтест"][k] for k in indicators) == (2, 1, 1, 0)
    assert tuple(rows["ИП Петров"][k] for k in indicators) == (1, 0, 1, 1)
    assert summary["total"] == {"issued": 3, "reported": 1, "not_reported": 2, "unplanned": 1}
    assert summary["missing_days"] == [START + timedelta(days=1)]


async def test_contractor_summary_agrees_with_the_results_table(async_test_session):
    await _seed_summary_day(async_test_session)

    summary = await _service(async_test_session).contractor_summary(housing_id=HOUSING, date_from=START, date_to=START)

    rows = await _rows(async_test_session, START)
    unplanned = sum(r.status == ReconciliationStatus.UNPLANNED for r in rows)
    assert summary["total"]["issued"] == len(rows) - unplanned
    assert summary["total"]["unplanned"] == unplanned
    assert summary["total"]["reported"] + summary["total"]["not_reported"] == summary["total"]["issued"]
    assert summary["missing_days"] == []


async def test_contractor_summary_narrows_to_the_selected_contractor(async_test_session):
    await _seed_summary_day(async_test_session)

    summary = await _service(async_test_session).contractor_summary(
        housing_id=HOUSING, date_from=START, date_to=START, contractor_id=CONTRACTOR_2
    )

    assert [item["contractor_id"] for item in summary["items"]] == [CONTRACTOR_2]
    assert summary["total"] == {"issued": 1, "reported": 0, "not_reported": 1, "unplanned": 1}
