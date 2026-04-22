"""
Tests for POST /api/v1/sync/* endpoints.

ReportClient is mocked so no real Raport connection is required.
Each test verifies:
  - the endpoint returns 200 with counts in `data`;
  - the upserted rows are actually present in the test database.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

RAPORT_PROJECT_ID = str(uuid.uuid4())
RAPORT_QUEUE_ID = str(uuid.uuid4())
RAPORT_CO_ID = str(uuid.uuid4())
RAPORT_HOUSING_ID = str(uuid.uuid4())
RAPORT_SECTION_ID = str(uuid.uuid4())
RAPORT_FLOOR_ID = str(uuid.uuid4())
RAPORT_CONTRACTOR_ID = str(uuid.uuid4())
RAPORT_WORK_GROUP_ID = str(uuid.uuid4())
RAPORT_WORK_TYPE_ID = str(uuid.uuid4())


def _paginated(items: list) -> dict:
    """Wrap items in the Raport list-response envelope."""
    return {"data": items, "pagination": {"total": len(items), "page": 1, "per_page": 200}}


def _make_report_client_mock() -> MagicMock:
    """Return a fully-configured ReportClient mock covering all sync methods."""
    mock = MagicMock()

    mock.list_projects = AsyncMock(
        return_value=_paginated(
            [{"id": RAPORT_PROJECT_ID, "name": "ЖК Тест", "description": "Тестовый проект", "class": "Комфорт"}]
        )
    )
    mock.list_project_queues = AsyncMock(
        return_value=_paginated([{"id": RAPORT_QUEUE_ID, "name": "Очередь 1"}])
    )
    mock.list_queue_construction_objects = AsyncMock(
        return_value=_paginated(
            [{"id": RAPORT_CO_ID, "name": "Корпус 5", "description": None, "planned_end_date": None}]
        )
    )
    mock.list_construction_object_housings = AsyncMock(
        return_value=_paginated(
            [{"id": RAPORT_HOUSING_ID, "name": "Корпус 5А", "complex_name": "ЖК Тест"}]
        )
    )
    mock.list_housing_sections = AsyncMock(
        return_value=_paginated(
            [{"id": RAPORT_SECTION_ID, "name": "Секция 1", "number": 1}]
        )
    )
    mock.list_section_floors = AsyncMock(
        return_value=_paginated(
            [{"id": RAPORT_FLOOR_ID, "name": "1 этаж", "number": 1}]
        )
    )
    mock.list_contractors = AsyncMock(
        return_value=_paginated(
            [
                {
                    "id": RAPORT_CONTRACTOR_ID,
                    "name": "ООО Рапорт Строй",
                    "short_name": "Рапорт Строй",
                    "inn": "9876543210",
                    "description": "Подрядчик из Рапорта",
                }
            ]
        )
    )
    mock.list_work_groups = AsyncMock(
        return_value=_paginated(
            [{"id": RAPORT_WORK_GROUP_ID, "name": "Монолит", "code": "MONOLITH", "description": None}]
        )
    )
    mock.list_work_group_work_types = AsyncMock(
        return_value=_paginated(
            [
                {
                    "id": RAPORT_WORK_TYPE_ID,
                    "name": "Заливка перекрытий",
                    "code": "FLOOR_POUR",
                    "unit": "м²",
                    "description": None,
                }
            ]
        )
    )

    return mock


# ---------------------------------------------------------------------------
# sync/contractors
# ---------------------------------------------------------------------------

@pytest.mark.smoke
async def test_sync_contractors_returns_200(client):
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        response = await client.post("/api/v1/sync/contractors")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["contractors"] == 1


async def test_sync_contractors_upserts_row(client, async_test_session):
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        await client.post("/api/v1/sync/contractors")

    from src.models import managers
    contractor = await managers.ContractorManager(async_test_session).search(
        raport_id=RAPORT_CONTRACTOR_ID
    )
    assert len(contractor) == 1
    assert contractor[0].name == "ООО Рапорт Строй"
    assert contractor[0].inn == "9876543210"


async def test_sync_contractors_idempotent(client):
    """Running sync twice must not duplicate rows."""
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        await client.post("/api/v1/sync/contractors")
        response = await client.post("/api/v1/sync/contractors")

    assert response.status_code == 200
    assert response.json()["data"]["contractors"] == 1


# ---------------------------------------------------------------------------
# sync/work-catalog
# ---------------------------------------------------------------------------

@pytest.mark.smoke
async def test_sync_work_catalog_returns_200(client):
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        response = await client.post("/api/v1/sync/work-catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["work_groups"] == 1
    assert body["data"]["work_types"] == 1


async def test_sync_work_catalog_upserts_rows(client, async_test_session):
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        await client.post("/api/v1/sync/work-catalog")

    from src.models import managers

    groups = await managers.WorkGroupManager(async_test_session).search(
        raport_id=RAPORT_WORK_GROUP_ID
    )
    assert len(groups) == 1
    assert groups[0].code == "MONOLITH"

    types = await managers.WorkTypeManager(async_test_session).search(
        raport_id=RAPORT_WORK_TYPE_ID
    )
    assert len(types) == 1
    assert types[0].code == "FLOOR_POUR"
    assert types[0].unit == "м²"


async def test_sync_work_catalog_idempotent(client):
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        await client.post("/api/v1/sync/work-catalog")
        response = await client.post("/api/v1/sync/work-catalog")

    assert response.status_code == 200
    assert response.json()["data"]["work_groups"] == 1


# ---------------------------------------------------------------------------
# sync/objects
# ---------------------------------------------------------------------------

@pytest.mark.smoke
async def test_sync_objects_returns_200(client):
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        response = await client.post("/api/v1/sync/objects")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["projects"] == 1
    assert body["data"]["construction_objects"] == 1
    assert body["data"]["housings"] == 1
    assert body["data"]["sections"] == 1
    assert body["data"]["floors"] == 1


async def test_sync_objects_upserts_full_hierarchy(client, async_test_session):
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        await client.post("/api/v1/sync/objects")

    from src.models import managers

    projects = await managers.WfProjectManager(async_test_session).search(
        raport_id=RAPORT_PROJECT_ID
    )
    assert len(projects) == 1
    assert projects[0].name == "ЖК Тест"

    objects = await managers.WfProjectObjectManager(async_test_session).search(
        raport_id=RAPORT_CO_ID
    )
    assert len(objects) == 1
    assert objects[0].name == "Корпус 5"

    housings = await managers.HousingManager(async_test_session).search(
        raport_id=RAPORT_HOUSING_ID
    )
    assert len(housings) == 1
    assert housings[0].name == "Корпус 5А"

    sections = await managers.SectionManager(async_test_session).search(
        raport_id=RAPORT_SECTION_ID
    )
    assert len(sections) == 1
    assert sections[0].section_number == 1

    floors = await managers.FloorManager(async_test_session).search(
        raport_id=RAPORT_FLOOR_ID
    )
    assert len(floors) == 1
    assert floors[0].floor_number == 1


async def test_sync_objects_filtered_by_project(client):
    """project_raport_id filter must limit sync to one project."""
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        response = await client.post(
            "/api/v1/sync/objects",
            params={"project_raport_id": RAPORT_PROJECT_ID},
        )

    assert response.status_code == 200
    assert response.json()["data"]["projects"] == 1


async def test_sync_objects_filtered_unknown_project(client):
    """Unknown project_raport_id must return counts of 0 (nothing to sync)."""
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        response = await client.post(
            "/api/v1/sync/objects",
            params={"project_raport_id": str(uuid.uuid4())},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["projects"] == 0


async def test_sync_objects_idempotent(client):
    mock = _make_report_client_mock()
    with patch("src.services.sync.service.ReportClient", return_value=mock):
        await client.post("/api/v1/sync/objects")
        response = await client.post("/api/v1/sync/objects")

    assert response.status_code == 200
    assert response.json()["data"]["projects"] == 1
