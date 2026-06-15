"""
Tests for POST /api/v1/sync/* endpoints.

ReportApi is mocked so no real Raport connection is required: the mock's
`list_all(method_name, **kwargs)` dispatches to canned, already-flattened
item lists (pagination lives inside ReportApi, which is replaced wholesale).
Each test verifies:
  - the endpoint returns 200 with counts in `data`;
  - the upserted rows are actually present in the test database.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.constants import API

RAPORT_PROJECT_ID = str(uuid.uuid4())
RAPORT_QUEUE_ID = str(uuid.uuid4())
RAPORT_CO_ID = str(uuid.uuid4())
RAPORT_HOUSING_ID = str(uuid.uuid4())
RAPORT_SECTION_ID = str(uuid.uuid4())
RAPORT_FLOOR_ID = str(uuid.uuid4())
RAPORT_CONTRACTOR_ID = str(uuid.uuid4())
RAPORT_CONTRACT_ID = str(uuid.uuid4())
RAPORT_USER_ID = str(uuid.uuid4())
# Terminology (docs/sync-mapping.md §3): Raport WorkGroup is transit-only;
# Raport WorkType → local WorkGroup; Raport Work → local WorkType.
RAPORT_WORK_GROUP_ID = str(uuid.uuid4())  # Raport WorkGroup (traversed, not stored)
RAPORT_WORK_TYPE_ID = str(uuid.uuid4())  # Raport WorkType → local WorkGroup
RAPORT_WORK_ID = str(uuid.uuid4())  # Raport Work → local WorkType
RAPORT_WORK_ID_2 = str(uuid.uuid4())  # second Raport Work → second local WorkType
RAPORT_TEMPLATE_ID = str(uuid.uuid4())  # default plan-template id
TASK_1_ID = str(uuid.uuid4())
TASK_2_ID = str(uuid.uuid4())


def _make_report_api_mock(overrides: dict | None = None) -> MagicMock:
    """Return a ReportApi mock whose `list_all` dispatches by endpoint method name.

    `overrides` replaces specific method pages (e.g. an empty assignments snapshot).
    """
    pages: dict[str, list[dict]] = {
        "list_projects": [
            {"id": RAPORT_PROJECT_ID, "name": "ЖК Тест", "description": "Тестовый проект", "class": "Комфорт"}
        ],
        "list_project_queues": [{"id": RAPORT_QUEUE_ID, "name": "Очередь 1"}],
        "list_queue_construction_objects": [
            {"id": RAPORT_CO_ID, "name": "Корпус 5", "description": None, "planned_end_date": None}
        ],
        "list_construction_object_housings": [
            {"id": RAPORT_HOUSING_ID, "name": "Корпус 5А", "complex_name": "ЖК Тест"}
        ],
        "list_housing_sections": [{"id": RAPORT_SECTION_ID, "name": "Секция 1", "number": 1}],
        "list_section_floors": [{"id": RAPORT_FLOOR_ID, "name": "1 этаж", "number": 1}],
        "list_contractors": [
            {
                "id": RAPORT_CONTRACTOR_ID,
                "name": "ООО Рапорт Строй",
                "short_name": "Рапорт Строй",
                "inn": "9876543210",
                "description": "Подрядчик из Рапорта",
            }
        ],
        "list_users": [
            {
                "id": RAPORT_USER_ID,
                "last_name": "Иванов",
                "first_name": "Иван",
                "middle_name": "Иванович",
                "shown_name": "Иванов Иван",
                "email": "ivanov@fsk.ru",
                "is_external": True,
                "groups": ["contractor", "smr_management_user"],
                "projects": [{"id": RAPORT_PROJECT_ID, "name": "ЖК Тест"}],
                "contractors": [{"id": RAPORT_CONTRACTOR_ID, "name": "ООО Рапорт Строй"}],
            }
        ],
        "list_contracts": [
            {
                "id": RAPORT_CONTRACT_ID,
                "contractor_id": RAPORT_CONTRACTOR_ID,
                "name": "Договор №1",
                "subject": "Комплекс монтажных работ",
                "is_warranty_letter": False,
            }
        ],
        # Raport WorkGroup — traversed only, not stored locally.
        "list_work_groups": [{"id": RAPORT_WORK_GROUP_ID, "name": "Монолит"}],
        # Raport WorkType → local WorkGroup («Виды работ»).
        "list_work_group_work_types": [{"id": RAPORT_WORK_TYPE_ID, "name": "Монтаж ЖБИ"}],
        # Raport Work → local WorkType («Работы»); unit taken from the default unit.
        "list_work_type_works": [
            {
                "id": RAPORT_WORK_ID,
                "name": "Заливка перекрытий",
                "units": [
                    {"id": str(uuid.uuid4()), "name": "м²", "is_default": True},
                    {"id": str(uuid.uuid4()), "name": "%", "is_default": False},
                ],
                "work_type": {"id": RAPORT_WORK_TYPE_ID, "name": "Монтаж ЖБИ"},
            },
            {
                "id": RAPORT_WORK_ID_2,
                "name": "Демонтаж",
                "units": [{"id": str(uuid.uuid4()), "name": "шт", "is_default": True}],
                "work_type": {"id": RAPORT_WORK_TYPE_ID, "name": "Монтаж ЖБИ"},
            },
        ],
        # Aggregated assignment: work_group is the (ignored) Raport WorkGroup;
        # each work_type is a Raport WorkType → a local WorkGroup.
        "list_assignments_aggregated": [
            {
                "contractor": {"id": RAPORT_CONTRACTOR_ID, "name": "ООО Рапорт Строй"},
                "housing": {"id": RAPORT_HOUSING_ID, "name": "Корпус 5А"},
                "section": {"id": RAPORT_SECTION_ID, "name": "Секция 1"},
                "work_group": {"id": RAPORT_WORK_GROUP_ID, "name": "Монолит"},
                "work_types": [{"id": RAPORT_WORK_TYPE_ID, "name": "Монтаж ЖБИ"}],
            }
        ],
    }
    overrides = overrides or {}
    # `plan` override lets a test supply an empty/custom tech-sequence snapshot.
    plan = overrides.pop("plan", _DEFAULT_PLAN)
    pages.update(overrides)

    async def _list_all(method_name: str, **kwargs) -> list[dict]:
        return pages.get(method_name, [])

    mock = MagicMock()
    mock.list_all = AsyncMock(side_effect=_list_all)
    # Plan endpoints for tech-sequence sync (no calendar plan → default template).
    mock.check_calendar_plan = AsyncMock(return_value={"is_exists": False, "data": []})
    mock.list_plan_templates = AsyncMock(
        return_value={"data": [{"id": RAPORT_TEMPLATE_ID, "is_default": True}], "pagination": {}}
    )
    mock.get_plan_template_data = AsyncMock(return_value={"plan": plan})
    mock.get_calendar_plan = AsyncMock(return_value={"plan": plan})
    return mock


# Default plan: task T2 (work #2) depends on task T1 (work #1).
_DEFAULT_PLAN = {
    "data": [
        {"id": TASK_1_ID, "line_number": 1, "duration": 10, "lag": 0, "work": {"id": RAPORT_WORK_ID}},
        {"id": TASK_2_ID, "line_number": 2, "duration": 20, "lag": 2, "work": {"id": RAPORT_WORK_ID_2}},
    ],
    "links": [{"id": str(uuid.uuid4()), "source": TASK_1_ID, "target": TASK_2_ID, "type": "0", "lag": 0}],
}


# ---------------------------------------------------------------------------
# sync/contractors
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_sync_contractors_returns_200(client):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(f"{API}/sync/contractors")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["contractors"] == 1


async def test_sync_contractors_upserts_row(client, async_test_session):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/contractors")

    from src.models import managers

    contractor = await managers.ContractorManager(async_test_session).search(raport_id=RAPORT_CONTRACTOR_ID)
    assert len(contractor) == 1
    assert contractor[0].name == "ООО Рапорт Строй"
    assert contractor[0].inn == "9876543210"


async def test_sync_contractors_idempotent(client):
    """Running sync twice must not duplicate rows."""
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/contractors")
        response = await client.post(f"{API}/sync/contractors")

    assert response.status_code == 200
    assert response.json()["data"]["contractors"] == 1


# ---------------------------------------------------------------------------
# sync/work-catalog
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_sync_work_catalog_returns_200(client):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(f"{API}/sync/work-catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["work_groups"] == 1
    assert body["data"]["work_types"] == 2


async def test_sync_work_catalog_upserts_rows(client, async_test_session):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/work-catalog")

    from src.models import managers

    # local WorkGroup («Виды работ») comes from the Raport WorkType
    groups = await managers.WorkGroupManager(async_test_session).search(raport_id=RAPORT_WORK_TYPE_ID)
    assert len(groups) == 1
    assert groups[0].name == "Монтаж ЖБИ"
    assert groups[0].code == RAPORT_WORK_TYPE_ID
    # the Raport WorkGroup itself must not be stored
    assert await managers.WorkGroupManager(async_test_session).search(raport_id=RAPORT_WORK_GROUP_ID) == []

    # local WorkType («Работы») comes from the Raport Work, nested under the local WorkGroup
    types = await managers.WorkTypeManager(async_test_session).search(raport_id=RAPORT_WORK_ID)
    assert len(types) == 1
    assert types[0].name == "Заливка перекрытий"
    assert types[0].code == RAPORT_WORK_ID
    assert types[0].unit == "м²"  # default unit
    assert types[0].group_id == groups[0].id


async def test_sync_work_catalog_idempotent(client):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/work-catalog")
        response = await client.post(f"{API}/sync/work-catalog")

    assert response.status_code == 200
    assert response.json()["data"]["work_groups"] == 1


# ---------------------------------------------------------------------------
# sync/objects
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_sync_objects_returns_200(client):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(f"{API}/sync/objects")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["projects"] == 1
    assert body["data"]["construction_objects"] == 1
    assert body["data"]["housings"] == 1
    assert body["data"]["sections"] == 1
    assert body["data"]["floors"] == 1


async def test_sync_objects_upserts_full_hierarchy(client, async_test_session):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/objects")

    from src.models import managers

    projects = await managers.WfProjectManager(async_test_session).search(raport_id=RAPORT_PROJECT_ID)
    assert len(projects) == 1
    assert projects[0].name == "ЖК Тест"

    objects = await managers.WfProjectObjectManager(async_test_session).search(raport_id=RAPORT_CO_ID)
    assert len(objects) == 1
    assert objects[0].name == "Корпус 5"

    housings = await managers.HousingManager(async_test_session).search(raport_id=RAPORT_HOUSING_ID)
    assert len(housings) == 1
    assert housings[0].name == "Корпус 5А"

    sections = await managers.SectionManager(async_test_session).search(raport_id=RAPORT_SECTION_ID)
    assert len(sections) == 1
    assert sections[0].section_number == 1

    floors = await managers.FloorManager(async_test_session).search(raport_id=RAPORT_FLOOR_ID)
    assert len(floors) == 1
    assert floors[0].floor_number == 1


async def test_sync_objects_filtered_by_project(client):
    """project_raport_id filter must limit sync to one project."""
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(
            f"{API}/sync/objects",
            params={"project_raport_id": RAPORT_PROJECT_ID},
        )

    assert response.status_code == 200
    assert response.json()["data"]["projects"] == 1


async def test_sync_objects_filtered_unknown_project(client):
    """Unknown project_raport_id must return counts of 0 (nothing to sync)."""
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(
            f"{API}/sync/objects",
            params={"project_raport_id": str(uuid.uuid4())},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["projects"] == 0


async def test_sync_objects_idempotent(client):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/objects")
        response = await client.post(f"{API}/sync/objects")

    assert response.status_code == 200
    assert response.json()["data"]["projects"] == 1


# ---------------------------------------------------------------------------
# sync/users
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_sync_users_upserts_row(client, async_test_session):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(f"{API}/sync/users")

    assert response.status_code == 200
    assert response.json()["data"]["users"] == 1

    from src.models import managers

    users = await managers.UserManager(async_test_session).search(raport_id=RAPORT_USER_ID)
    assert len(users) == 1
    user = users[0]
    assert user.shown_name == "Иванов Иван"
    assert user.email == "ivanov@fsk.ru"
    assert user.is_external is True
    assert "contractor" in user.groups
    assert user.project_ids == [RAPORT_PROJECT_ID]
    assert user.contractor_ids == [RAPORT_CONTRACTOR_ID]


# ---------------------------------------------------------------------------
# sync/contracts
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_sync_contracts_resolves_contractor(client, async_test_session):
    """Contract's Raport contractor_id is resolved to the local contractor."""
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/contractors")
        response = await client.post(f"{API}/sync/contracts")

    assert response.status_code == 200
    assert response.json()["data"]["contracts"] == 1

    from src.models import managers

    contractor = (await managers.ContractorManager(async_test_session).search(raport_id=RAPORT_CONTRACTOR_ID))[0]
    contracts = await managers.ContractManager(async_test_session).search(raport_id=RAPORT_CONTRACT_ID)
    assert len(contracts) == 1
    assert contracts[0].subject == "Комплекс монтажных работ"
    assert contracts[0].contractor_id == contractor.id
    assert contracts[0].is_warranty_letter is False


# ---------------------------------------------------------------------------
# sync/assignments
# ---------------------------------------------------------------------------


async def _sync_assignment_prerequisites(client):
    """Sync the contractor/housing/section/work_group an assignment resolves against."""
    await client.post(f"{API}/sync/contractors")
    await client.post(f"{API}/sync/objects")
    await client.post(f"{API}/sync/work-catalog")


@pytest.mark.smoke
async def test_sync_assignments_explodes_and_resolves(client, async_test_session):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await _sync_assignment_prerequisites(client)
        response = await client.post(f"{API}/sync/assignments")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["assignments"] == 1
    assert data["skipped"] == 0

    from src.models import managers

    # local WorkGroup resolved from the Raport WorkType id
    work_group = (await managers.WorkGroupManager(async_test_session).search(raport_id=RAPORT_WORK_TYPE_ID))[0]
    contractor = (await managers.ContractorManager(async_test_session).search(raport_id=RAPORT_CONTRACTOR_ID))[0]

    rows = await managers.ContractorAssignmentManager(async_test_session).search(
        contractor_id=contractor.id, work_group_id=work_group.id
    )
    assert len(rows) == 1
    assert rows[0].source == "raport"
    assert rows[0].work_type_ids == []


async def test_sync_assignments_snapshot_delete(client, async_test_session):
    """A raport assignment missing from the new snapshot is deleted within scope."""
    with patch("src.services.sync.service.ReportApi", return_value=_make_report_api_mock()):
        await _sync_assignment_prerequisites(client)
        await client.post(f"{API}/sync/assignments", params={"housing_raport_id": RAPORT_HOUSING_ID})

    # re-sync the same housing with an empty aggregate → the row is reconciled away
    empty = _make_report_api_mock(overrides={"list_assignments_aggregated": []})
    with patch("src.services.sync.service.ReportApi", return_value=empty):
        resp = await client.post(f"{API}/sync/assignments", params={"housing_raport_id": RAPORT_HOUSING_ID})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["assignments"] == 0
    assert data["deleted"] >= 1

    from src.models import managers

    housing = (await managers.HousingManager(async_test_session).search(raport_id=RAPORT_HOUSING_ID))[0]
    remaining = await managers.ContractorAssignmentManager(async_test_session).search(
        housing_id=housing.id, source="raport"
    )
    assert remaining == []


# ---------------------------------------------------------------------------
# sync/tech-sequence
# ---------------------------------------------------------------------------


async def _sync_tech_sequence_prerequisites(client):
    await client.post(f"{API}/sync/work-catalog")
    await client.post(f"{API}/sync/objects")


@pytest.mark.smoke
async def test_sync_tech_sequence_builds_from_template(client, async_test_session):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await _sync_tech_sequence_prerequisites(client)
        response = await client.post(f"{API}/sync/tech-sequence", params={"housing_raport_id": RAPORT_HOUSING_ID})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tech_sequence"] == 2
    assert data["skipped"] == 0

    from src.models import managers

    wt1 = (await managers.WorkTypeManager(async_test_session).search(raport_id=RAPORT_WORK_ID))[0]
    wt2 = (await managers.WorkTypeManager(async_test_session).search(raport_id=RAPORT_WORK_ID_2))[0]
    housing = (await managers.HousingManager(async_test_session).search(raport_id=RAPORT_HOUSING_ID))[0]

    items = await managers.TechSequenceItemManager(async_test_session).search(housing_id=housing.id, source="raport")
    by_wt = {i.work_type_id: i for i in items}
    assert len(by_wt) == 2
    # task T2 (wt2) depends on task T1 (wt1)
    assert by_wt[wt2.id].depends_on == [str(wt1.id)]
    assert by_wt[wt2.id].order == 2
    assert by_wt[wt2.id].lag_days == 2
    assert by_wt[wt2.id].estimated_days == 20
    assert by_wt[wt2.id].source == "raport"
    # wt1 is the root — no predecessors
    assert by_wt[wt1.id].depends_on == []
    assert by_wt[wt1.id].order == 1


async def test_sync_tech_sequence_snapshot_delete(client, async_test_session):
    with patch("src.services.sync.service.ReportApi", return_value=_make_report_api_mock()):
        await _sync_tech_sequence_prerequisites(client)
        await client.post(f"{API}/sync/tech-sequence", params={"housing_raport_id": RAPORT_HOUSING_ID})

    # re-sync with an empty plan → all raport rows for the housing are reconciled away
    empty = _make_report_api_mock(overrides={"plan": {"data": [], "links": []}})
    with patch("src.services.sync.service.ReportApi", return_value=empty):
        resp = await client.post(f"{API}/sync/tech-sequence", params={"housing_raport_id": RAPORT_HOUSING_ID})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tech_sequence"] == 0
    assert data["deleted"] >= 2

    from src.models import managers

    housing = (await managers.HousingManager(async_test_session).search(raport_id=RAPORT_HOUSING_ID))[0]
    remaining = await managers.TechSequenceItemManager(async_test_session).search(
        housing_id=housing.id, source="raport"
    )
    assert remaining == []


# ---------------------------------------------------------------------------
# unified POST /sync (enum dispatcher)
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_sync_all_no_body_syncs_everything(client):
    """No body → every group is synced."""
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(f"{API}/sync")

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {
        "users",
        "contractors",
        "contracts",
        "objects",
        "work_catalog",
        "assignments",
        "tech_sequence",
    }
    assert data["users"]["users"] == 1
    assert data["contractors"]["contractors"] == 1
    assert data["contracts"]["contracts"] == 1
    assert data["objects"]["projects"] == 1
    assert data["work_catalog"]["work_groups"] == 1
    assert data["assignments"]["assignments"] == 1
    assert data["tech_sequence"]["tech_sequence"] >= 1


async def test_sync_all_subset_only_contractors(client):
    """entities=[contractors] → only the contractor group runs."""
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(f"{API}/sync", json={"entities": ["contractors"]})

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"contractors"}


async def test_sync_all_object_entity_triggers_objects_group(client):
    """A single object-level entity (housings) triggers the whole objects traversal."""
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        response = await client.post(f"{API}/sync", json={"entities": ["housings"]})

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"objects"}
    assert data["objects"]["housings"] == 1
