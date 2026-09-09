"""Scheduled work — the logic behind the endpoints Raport's taskiq calls.

plan-naryad runs no scheduler of its own; the bodies live in TaskService and are covered
here, especially the isolation guarantee: one broken housing must not cost the others
their plan.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from src.models import managers
from src.models.dbo.tables.plan import PlanStatus
from src.services.task import TaskService

HOUSING = UUID("11111111-1111-1111-1111-111111111111")
RAPORT_HOUSING = "10000000-0000-0000-0000-000000000001"
SECTION_1 = UUID("33333333-3333-3333-3333-333333333333")
FLOOR_1 = UUID("55555555-5555-5555-5555-555555555555")
WORK_A = UUID("88888888-8888-8888-8888-888888888888")
CONTRACTOR = UUID("99999999-9999-9999-9999-999999999999")

DAY = date(2026, 10, 5)


async def _sequence(session) -> None:
    manager = managers.TechSequenceItemManager(session)
    for existing in await manager.search(housing_id=HOUSING):
        await manager.delete_by_id(existing.id)
    await manager.create(
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


async def _clear_plan(session) -> None:
    plans = managers.PlanItemManager(session)
    for item in await plans.search(housing_id=HOUSING, date=DAY):
        await plans.delete_by_id(item.id)


@pytest.mark.smoke
async def test_housings_with_sequence_lists_only_synced_ones(async_test_session):
    await _sequence(async_test_session)

    rows = await TaskService(async_test_session).housings_with_sequence()

    assert (HOUSING, RAPORT_HOUSING) in rows


@pytest.mark.smoke
async def test_nightly_syncs_facts_then_generates(async_test_session):
    await _sequence(async_test_session)
    await _clear_plan(async_test_session)

    with (
        patch(
            "src.services.task.service.SyncReportService.sync_work_facts",
            new=AsyncMock(return_value={"work_facts": 7}),
        ),
        patch(
            "src.services.task.service.AutogenerationService.generate_daily_plan",
            new=AsyncMock(return_value=([1, 2, 3], [])),
        ),
    ):
        result = await TaskService(async_test_session).run_nightly_plan(
            target_date=DAY, housing_raport_id=RAPORT_HOUSING
        )

    assert result["date"] == DAY
    assert result["facts"] == 7
    assert result["positions"] == 3
    assert result["failed"] == 0


async def test_nightly_reports_the_facts_window(async_test_session):
    """The nightly run wants yesterday and today, so a late fact is not missed."""
    await _sequence(async_test_session)
    sync = AsyncMock(return_value={"work_facts": 0})

    with (
        patch("src.services.task.service.SyncReportService.sync_work_facts", new=sync),
        patch(
            "src.services.task.service.AutogenerationService.generate_daily_plan",
            new=AsyncMock(return_value=([], [])),
        ),
    ):
        await TaskService(async_test_session).run_nightly_plan(target_date=DAY, housing_raport_id=RAPORT_HOUSING)

    assert sync.await_args.kwargs["date_from"] == DAY - timedelta(days=1)
    assert sync.await_args.kwargs["date_to"] == DAY


async def test_a_broken_housing_does_not_stop_the_rest(async_test_session):
    """Isolation is the point of the per-housing try block."""
    await _sequence(async_test_session)

    with (
        patch(
            "src.services.task.service.SyncReportService.sync_work_facts",
            new=AsyncMock(side_effect=RuntimeError("Raport 503")),
        ),
        patch(
            "src.services.task.service.AutogenerationService.generate_daily_plan",
            new=AsyncMock(return_value=([1], [])),
        ),
    ):
        result = await TaskService(async_test_session).run_nightly_plan(
            target_date=DAY, housing_raport_id=RAPORT_HOUSING
        )

    # Facts failed, generation still ran — and the failure is reported, not swallowed.
    assert result["failed"] == 1
    assert result["positions"] == 1
    assert "sync_work_facts" in result["housings_detail"][0]["errors"][0]


async def test_a_failed_step_is_rolled_back_and_the_session_stays_usable(async_test_session):
    """The night of the dead connection: the run shares one session across ~550 housings.

    A step that fails halfway must not leave its writes pending for the next housing's commit
    to pick up, and must not leave the session in the «rollback first» state that turned one
    dead connection into a failed run.
    """
    await _sequence(async_test_session)
    await _clear_plan(async_test_session)
    plans = managers.PlanItemManager(async_test_session)

    async def half_done_then_dead(**kwargs):
        await plans.bulk_insert(
            [
                {
                    "date": DAY,
                    "housing_id": HOUSING,
                    "section_id": SECTION_1,
                    "floor_id": FLOOR_1,
                    "work_id": WORK_A,
                    "contractor_id": CONTRACTOR,
                    "source": "auto",
                    "status": PlanStatus.DRAFT.value,
                }
            ]
        )
        raise RuntimeError("cannot call PreparedStatement.fetch(): underlying connection is closed")

    with (
        patch(
            "src.services.task.service.SyncReportService.sync_work_facts",
            new=AsyncMock(return_value={"work_facts": 0}),
        ),
        patch(
            "src.services.task.service.AutogenerationService.generate_daily_plan",
            new=AsyncMock(side_effect=half_done_then_dead),
        ),
    ):
        result = await TaskService(async_test_session).run_nightly_plan(
            target_date=DAY, housing_raport_id=RAPORT_HOUSING
        )

    assert result["failed"] == 1
    assert "connection is closed" in result["housings_detail"][0]["errors"][0]
    # The pending insert was rolled back, not left for somebody else's commit.
    assert await plans.search(housing_id=HOUSING, date=DAY) == []
    # And the session works again: a plain query on it succeeds.
    assert await managers.HousingManager(async_test_session).get_by_id(HOUSING) is not None


async def test_the_run_continues_past_a_dead_transaction(async_test_session):
    await _sequence(async_test_session)
    await _clear_plan(async_test_session)

    with (
        patch.object(
            TaskService,
            "housings_with_sequence",
            new=AsyncMock(return_value=[(HOUSING, RAPORT_HOUSING), (HOUSING, RAPORT_HOUSING)]),
        ),
        patch(
            "src.services.task.service.SyncReportService.sync_work_facts",
            new=AsyncMock(return_value={"work_facts": 0}),
        ),
        patch(
            "src.services.task.service.AutogenerationService.generate_daily_plan",
            new=AsyncMock(side_effect=[RuntimeError("underlying connection is closed"), ([1, 2], [])]),
        ),
    ):
        result = await TaskService(async_test_session).run_nightly_plan(target_date=DAY)

    assert result["housings"] == 2
    assert result["failed"] == 1
    assert result["positions"] == 2


async def test_generation_failure_is_reported_too(async_test_session):
    await _sequence(async_test_session)

    with (
        patch(
            "src.services.task.service.SyncReportService.sync_work_facts",
            new=AsyncMock(return_value={"work_facts": 1}),
        ),
        patch(
            "src.services.task.service.AutogenerationService.generate_daily_plan",
            new=AsyncMock(side_effect=RuntimeError("no calendar plan")),
        ),
    ):
        result = await TaskService(async_test_session).run_nightly_plan(
            target_date=DAY, housing_raport_id=RAPORT_HOUSING
        )

    assert result["failed"] == 1
    assert "generate_daily_plan" in result["housings_detail"][0]["errors"][0]


async def test_empty_reasons_surface_when_nothing_was_generated(async_test_session):
    await _sequence(async_test_session)

    with (
        patch(
            "src.services.task.service.SyncReportService.sync_work_facts",
            new=AsyncMock(return_value={"work_facts": 0}),
        ),
        patch(
            "src.services.task.service.AutogenerationService.generate_daily_plan",
            new=AsyncMock(return_value=([], ["Не назначен подрядчик для работы X"])),
        ),
    ):
        result = await TaskService(async_test_session).run_nightly_plan(
            target_date=DAY, housing_raport_id=RAPORT_HOUSING
        )

    assert result["positions"] == 0
    assert result["housings_detail"][0]["reasons"] == ["Не назначен подрядчик для работы X"]


async def test_transfer_job_defaults_to_today(async_test_session):
    result = await TaskService(async_test_session).run_transfer()

    assert result["date"] == date.today()
    assert "transferred" in result


async def test_transfer_job_moves_the_day(async_test_session):
    await _clear_plan(async_test_session)
    await managers.PlanItemManager(async_test_session).create(
        {
            "date": DAY,
            "housing_id": HOUSING,
            "section_id": SECTION_1,
            "floor_id": FLOOR_1,
            "work_id": WORK_A,
            "contractor_id": CONTRACTOR,
            "source": "auto",
            "status": PlanStatus.DRAFT.value,
        }
    )

    result = await TaskService(async_test_session).run_transfer(target_date=DAY)

    assert result["transferred"] == 1
    items = await managers.PlanItemManager(async_test_session).search(housing_id=HOUSING, date=DAY)
    assert {i.status for i in items} == {PlanStatus.TRANSFERRED}


@pytest.mark.smoke
async def test_endpoints_are_callable(client, async_test_session):
    """Raport calls these by HTTP, so the wiring matters as much as the bodies."""
    from tests.constants import API

    await _clear_plan(async_test_session)

    with (
        patch(
            "src.services.task.service.SyncReportService.sync_work_facts",
            new=AsyncMock(return_value={"work_facts": 0}),
        ),
        patch(
            "src.services.task.service.AutogenerationService.generate_daily_plan",
            new=AsyncMock(return_value=([], [])),
        ),
    ):
        nightly = await client.post(
            f"{API}/tasks/nightly-plan",
            params={"date": str(DAY), "housing_raport_id": RAPORT_HOUSING},
        )
    transfer = await client.post(f"{API}/tasks/transfer", params={"date": str(DAY)})

    assert nightly.status_code == 200
    assert nightly.json()["data"]["housings"] == 1
    assert transfer.status_code == 200
    assert "transferred" in transfer.json()["data"]


async def test_nightly_never_forces_over_an_existing_day(async_test_session):
    """a day someone already built and confirmed must survive the night —
    the job only fills empty days, so the generate call must not carry force=True."""
    await _sequence(async_test_session)
    generate = AsyncMock(return_value=([], []))

    with (
        patch(
            "src.services.task.service.SyncReportService.sync_work_facts",
            new=AsyncMock(return_value={"work_facts": 0}),
        ),
        patch("src.services.task.service.AutogenerationService.generate_daily_plan", new=generate),
    ):
        await TaskService(async_test_session).run_nightly_plan(target_date=DAY, housing_raport_id=RAPORT_HOUSING)

    assert generate.call_args is not None
    assert generate.call_args.kwargs["force"] is False
