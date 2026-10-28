"""Attributing mirrored facts to contractors, with the Raport client mocked out.

The fact's own `work_cell_contractor` decides (Raport returns its contractor as `contractor`);
the cell's assignment is only a fallback for facts entered before DEV-6485.
"""

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
