"""Attributing mirrored facts to contractors, with the Raport client mocked out.

The fact's own `work_cell_contractor` decides (Raport returns its contractor as `contractor`);
the cell's assignment is only a fallback for facts entered before DEV-6485.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.models import managers
from src.services.sync.service import SyncReportService

HOUSING_RAPORT_ID = "10000000-0000-0000-0000-000000000001"
CONTRACTOR_1 = UUID("99999999-9999-9999-9999-999999999999")
CONTRACTOR_2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

RAPORT_SECTION_1 = "20000000-0000-0000-0000-000000000001"
RAPORT_FLOOR_1 = "30000000-0000-0000-0000-000000000001"
RAPORT_CONTRACTOR_1 = "40000000-0000-0000-0000-000000000001"
RAPORT_CONTRACTOR_2 = "40000000-0000-0000-0000-000000000002"
RAPORT_WORK_1 = "60000000-0000-0000-0000-000000000001"
UNKNOWN_RAPORT_CONTRACTOR = "4fffffff-0000-0000-0000-000000000000"


def _fact(raport_id: str, contractor_raport_id: str | None) -> dict:
    """One row of `GET /work-facts` → data[]."""
    return {
        "id": raport_id,
        "work_date": "2026-10-27",
        "section": {"id": RAPORT_SECTION_1},
        "floor": {"id": RAPORT_FLOOR_1},
        "work": {"id": RAPORT_WORK_1},
        "contractor": {"id": contractor_raport_id, "name": "ООО"} if contractor_raport_id else None,
        "work_cell_contractor_id": "eeee0000-0000-0000-0000-00000000000c" if contractor_raport_id else None,
        "volume": 0,
        "percent": 25,
    }


def _assignment(contractor_raport_id: str) -> dict:
    """One row of `GET /contractor-works` → data[] on the facts' cell."""
    return {
        "id": "eeee0000-0000-0000-0000-000000000001",
        "contractor": {"id": contractor_raport_id},
        "section": {"id": RAPORT_SECTION_1},
        "floor": {"id": RAPORT_FLOOR_1},
        "work": {"id": RAPORT_WORK_1},
    }


def _report_mock(facts: list[dict], assignments: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.list_work_facts = AsyncMock(return_value={"data": facts, "pagination": {}})
    mock.list_contractor_works = AsyncMock(return_value={"data": assignments, "pagination": {}})
    return mock


@pytest.fixture
async def synced_facts(async_test_session):
    """Run the facts sync against a mocked Raport and drop whatever it stored afterwards."""
    manager = managers.WorkFactManager(async_test_session)
    stored: list[str] = []

    async def run(facts: list[dict], assignments: list[dict]) -> tuple[dict, dict[str, UUID | None], MagicMock]:
        service = SyncReportService(async_test_session)
        service.report = _report_mock(facts, assignments)
        result = await service.sync_work_facts(HOUSING_RAPORT_ID)
        raport_ids = [f["id"] for f in facts]
        stored.extend(raport_ids)
        rows = await manager.search(raport_id__in=raport_ids)
        return result, {r.raport_id: r.contractor_id for r in rows}, service.report

    yield run

    if stored:
        rows = await manager.search(raport_id__in=stored)
        await manager.bulk_delete([r.id for r in rows])
        await async_test_session.commit()


@pytest.mark.smoke
async def test_fact_goes_to_its_own_contractor_on_a_shared_cell(synced_facts):
    """Two contractors on the cell: the old fallback could not tell them apart, wcc can."""
    fact_id = "f0000000-0000-0000-0000-000000000001"

    result, contractors, report = await synced_facts(
        [_fact(fact_id, RAPORT_CONTRACTOR_2)],
        [_assignment(RAPORT_CONTRACTOR_1), _assignment(RAPORT_CONTRACTOR_2)],
    )

    assert contractors[fact_id] == CONTRACTOR_2
    assert result["without_contractor"] == 0
    report.list_contractor_works.assert_not_called()


async def test_legacy_fact_falls_back_to_the_sole_assignee(synced_facts):
    fact_id = "f0000000-0000-0000-0000-000000000002"

    result, contractors, report = await synced_facts([_fact(fact_id, None)], [_assignment(RAPORT_CONTRACTOR_1)])

    assert contractors[fact_id] == CONTRACTOR_1
    assert result["without_contractor"] == 0
    report.list_contractor_works.assert_awaited()


async def test_legacy_fact_on_a_shared_cell_stays_unattributed(synced_facts):
    fact_id = "f0000000-0000-0000-0000-000000000003"

    result, contractors, _ = await synced_facts(
        [_fact(fact_id, None)],
        [_assignment(RAPORT_CONTRACTOR_1), _assignment(RAPORT_CONTRACTOR_2)],
    )

    assert contractors[fact_id] is None
    assert result["without_contractor"] == 1


async def test_unsynced_contractor_is_not_replaced_by_the_cell_assignee(synced_facts):
    """Raport named someone we do not know; crediting the cell's assignee would be a guess."""
    fact_id = "f0000000-0000-0000-0000-000000000004"

    result, contractors, _ = await synced_facts(
        [_fact(fact_id, UNKNOWN_RAPORT_CONTRACTOR)],
        [_assignment(RAPORT_CONTRACTOR_1)],
    )

    assert contractors[fact_id] is None
    assert result["without_contractor"] == 1


# ── Facts deleted in Raport leave the mirror ──────────────────────────────────

HOUSING_ID = UUID("11111111-1111-1111-1111-111111111111")
WINDOW_FROM = date(2026, 10, 20)
WINDOW_TO = date(2026, 10, 21)


@pytest.fixture
async def mirrored(async_test_session):
    """Local facts of housing 1 by raport_id (None for a row not mirrored from Raport)."""
    manager = managers.WorkFactManager(async_test_session)
    created: list[UUID] = []

    async def add(raport_id: str | None, work_date: date) -> UUID:
        fact = await manager.create(
            {
                "raport_id": raport_id,
                "work_date": work_date,
                "housing_id": HOUSING_ID,
                "section_id": UUID("33333333-3333-3333-3333-333333333333"),
                "floor_id": UUID("55555555-5555-5555-5555-555555555555"),
                "work_id": UUID("88888888-8888-8888-8888-888888888888"),
                "contractor_id": CONTRACTOR_1,
                "volume": 0,
                "percent": 30,
                "source": "raport" if raport_id else "contractor_web",
            }
        )
        created.append(fact.id)
        return fact.id

    yield add

    await manager.bulk_delete(created)
    await async_test_session.commit()


async def _existing(session, ids: list[UUID]) -> set[UUID]:
    return {f.id for f in await managers.WorkFactManager(session).search(id__in=ids)}


def _dated(raport_id: str, work_date: date) -> dict:
    return {**_fact(raport_id, RAPORT_CONTRACTOR_1), "work_date": str(work_date)}


@pytest.mark.smoke
async def test_fact_gone_from_raport_is_removed_within_the_window(async_test_session, mirrored):
    present = await mirrored("f1000000-0000-0000-0000-000000000001", WINDOW_FROM)
    vanished = await mirrored("f1000000-0000-0000-0000-000000000002", WINDOW_TO)
    outside = await mirrored("f1000000-0000-0000-0000-000000000003", WINDOW_TO + timedelta(days=3))
    local_only = await mirrored(None, WINDOW_FROM)
    service = SyncReportService(async_test_session)
    service.report = _report_mock([_dated("f1000000-0000-0000-0000-000000000001", WINDOW_FROM)], [])

    result = await service.sync_work_facts(HOUSING_RAPORT_ID, date_from=WINDOW_FROM, date_to=WINDOW_TO)

    assert (result["removed"], result["complete"]) == (1, True)
    assert await _existing(async_test_session, [present, vanished, outside, local_only]) == {
        present,
        outside,
        local_only,
    }


async def test_empty_answer_removes_the_whole_window(async_test_session, mirrored):
    vanished = await mirrored("f1000000-0000-0000-0000-000000000004", WINDOW_FROM)
    service = SyncReportService(async_test_session)
    service.report = _report_mock([], [])

    result = await service.sync_work_facts(HOUSING_RAPORT_ID, date_from=WINDOW_FROM, date_to=WINDOW_TO)

    assert result["removed"] == 1
    assert await _existing(async_test_session, [vanished]) == set()


async def test_nothing_is_removed_when_raport_is_read_partially(async_test_session, mirrored):
    """A page that failed to load must not make its facts look deleted."""
    kept = await mirrored("f1000000-0000-0000-0000-000000000005", WINDOW_FROM)
    service = SyncReportService(async_test_session)
    service.report = MagicMock()
    service.report.list_work_facts = AsyncMock(
        side_effect=[
            {"data": [_dated("f1000000-0000-0000-0000-000000000006", WINDOW_FROM)], "pagination": {"next_page": 2}},
            RuntimeError("Raport is down"),
        ]
    )
    service.report.list_contractor_works = AsyncMock(return_value={"data": [], "pagination": {}})

    result = await service.sync_work_facts(HOUSING_RAPORT_ID, date_from=WINDOW_FROM, date_to=WINDOW_TO)

    assert (result["removed"], result["complete"]) == (0, False)
    assert await _existing(async_test_session, [kept]) == {kept}
    stored = await managers.WorkFactManager(async_test_session).search(raport_id="f1000000-0000-0000-0000-000000000006")
    await managers.WorkFactManager(async_test_session).bulk_delete([f.id for f in stored])
    await async_test_session.commit()


async def test_window_reaches_the_end_of_its_last_day(async_test_session):
    service = SyncReportService(async_test_session)
    service.report = _report_mock([], [])

    await service.sync_work_facts(HOUSING_RAPORT_ID, date_from=WINDOW_FROM, date_to=WINDOW_TO)

    params = service.report.list_work_facts.call_args.kwargs
    assert (params["work_date__gte"], params["work_date__lte"]) == ("2026-10-20", "2026-10-21T23:59:59")
