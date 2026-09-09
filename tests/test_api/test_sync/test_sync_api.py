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
# Catalogue names now match Raport one-to-one (decision Р6b): work_set →
# work_group → work_type → work, all four stored locally.
RAPORT_WORK_SET_ID = str(uuid.uuid4())
RAPORT_WORK_GROUP_ID = str(uuid.uuid4())
RAPORT_WORK_TYPE_ID = str(uuid.uuid4())
RAPORT_WORK_ID = str(uuid.uuid4())
RAPORT_WORK_ID_2 = str(uuid.uuid4())
RAPORT_TEMPLATE_ID = str(uuid.uuid4())  # default plan-template id
TASK_1_ID = str(uuid.uuid4())
TASK_2_ID = str(uuid.uuid4())


def _make_report_api_mock(overrides: dict | None = None) -> MagicMock:
    """Return a ReportApi mock whose `list_all` dispatches by endpoint method name.

    `overrides` replaces specific method pages (e.g. a custom catalogue snapshot).
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
        "list_section_floors": [{"id": RAPORT_FLOOR_ID, "name": "1 этаж", "sort_order": 1}],
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
    }
    overrides = overrides or {}
    # `plan` override lets a test supply an empty/custom tech-sequence snapshot;
    # `has_calendar_plan=False` simulates a housing nobody planned (DEV-6936).
    plan = overrides.pop("plan", _DEFAULT_PLAN)
    has_calendar_plan = overrides.pop("has_calendar_plan", True)
    pages.update(overrides)

    async def _list_all(method_name: str, **kwargs) -> list[dict]:
        return pages.get(method_name, [])

    mock = MagicMock()
    mock.list_all = AsyncMock(side_effect=_list_all)

    async def _check_calendar_plan(**kwargs):
        if has_calendar_plan and not kwargs.get("section_id"):
            return {"is_exists": True, "data": [{"id": RAPORT_TEMPLATE_ID}]}
        return {"is_exists": False, "data": []}

    mock.check_calendar_plan = AsyncMock(side_effect=_check_calendar_plan)
    mock.list_plan_templates = AsyncMock(
        return_value={"data": [{"id": RAPORT_TEMPLATE_ID, "is_default": True}], "pagination": {}}
    )
    mock.get_works_structure = AsyncMock(return_value=overrides.get("works_structure", _DEFAULT_WORKS_STRUCTURE))
    mock.get_plan_template_data = AsyncMock(return_value={"plan": plan})
    mock.get_calendar_plan = AsyncMock(return_value={"plan": plan})
    return mock


# The whole catalogue arrives flat from GET /works/structure, one row per node:
# level 0 = work_set, 1 = work_group, 2 = work_type, 3 = work (the only level with units).
_DEFAULT_WORKS_STRUCTURE = {
    "data": [
        {"id": RAPORT_WORK_SET_ID, "parent_id": None, "title": "Этап 1", "level": 0},
        {"id": RAPORT_WORK_GROUP_ID, "parent_id": RAPORT_WORK_SET_ID, "title": "Монолит", "level": 1},
        {"id": RAPORT_WORK_TYPE_ID, "parent_id": RAPORT_WORK_GROUP_ID, "title": "Монтаж ЖБИ", "level": 2},
        {
            "id": RAPORT_WORK_ID,
            "parent_id": RAPORT_WORK_TYPE_ID,
            "title": "Заливка перекрытий",
            "level": 3,
            "units": [
                {"id": str(uuid.uuid4()), "name": "м²", "is_default": True},
                {"id": str(uuid.uuid4()), "name": "%", "is_default": False},
            ],
        },
        {
            "id": RAPORT_WORK_ID_2,
            "parent_id": RAPORT_WORK_TYPE_ID,
            "title": "Демонтаж",
            "level": 3,
            "units": [{"id": str(uuid.uuid4()), "name": "шт", "is_default": True}],
        },
    ]
}


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
    assert body["data"]["work_sets"] == 1
    assert body["data"]["work_groups"] == 1
    assert body["data"]["work_types"] == 1
    assert body["data"]["works"] == 2


async def test_sync_work_catalog_upserts_rows(client, async_test_session):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/work-catalog")

    from src.models import managers

    # All four levels land under their Raport names, each linked to the one above.
    sets = await managers.WorkSetManager(async_test_session).search(raport_id=RAPORT_WORK_SET_ID)
    assert len(sets) == 1
    assert sets[0].name == "Этап 1"

    groups = await managers.WorkGroupManager(async_test_session).search(raport_id=RAPORT_WORK_GROUP_ID)
    assert len(groups) == 1
    assert groups[0].name == "Монолит"
    assert groups[0].work_set_id == sets[0].id

    types = await managers.WorkTypeManager(async_test_session).search(raport_id=RAPORT_WORK_TYPE_ID)
    assert len(types) == 1
    assert types[0].name == "Монтаж ЖБИ"
    assert types[0].work_group_id == groups[0].id

    works = await managers.WorkManager(async_test_session).search(raport_id=RAPORT_WORK_ID)
    assert len(works) == 1
    assert works[0].name == "Заливка перекрытий"
    assert works[0].code == RAPORT_WORK_ID
    assert works[0].unit == "м²"  # default unit
    assert works[0].work_type_id == types[0].id


async def test_sync_work_catalog_idempotent(client):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await client.post(f"{API}/sync/work-catalog")
        response = await client.post(f"{API}/sync/work-catalog")

    assert response.status_code == 200
    assert response.json()["data"]["works"] == 2


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

    projects = await managers.ProjectManager(async_test_session).search(raport_id=RAPORT_PROJECT_ID)
    assert len(projects) == 1
    assert projects[0].name == "ЖК Тест"

    objects = await managers.ConstructionObjectManager(async_test_session).search(raport_id=RAPORT_CO_ID)
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


# ---------------------------------------------------------------------------
# sync/tech-sequence
# ---------------------------------------------------------------------------


async def _sync_tech_sequence_prerequisites(client):
    await client.post(f"{API}/sync/work-catalog")
    await client.post(f"{API}/sync/objects")


@pytest.mark.smoke
async def test_sync_tech_sequence_builds_from_calendar_plan(client, async_test_session):
    mock = _make_report_api_mock()
    with patch("src.services.sync.service.ReportApi", return_value=mock):
        await _sync_tech_sequence_prerequisites(client)
        response = await client.post(f"{API}/sync/tech-sequence", params={"housing_raport_id": RAPORT_HOUSING_ID})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tech_sequence"] == 2
    assert data["skipped"] == 0

    from src.models import managers

    wt1 = (await managers.WorkManager(async_test_session).search(raport_id=RAPORT_WORK_ID))[0]
    wt2 = (await managers.WorkManager(async_test_session).search(raport_id=RAPORT_WORK_ID_2))[0]
    housing = (await managers.HousingManager(async_test_session).search(raport_id=RAPORT_HOUSING_ID))[0]

    items = await managers.TechSequenceItemManager(async_test_session).search(housing_id=housing.id, source="raport")
    by_wt = {i.work_id: i for i in items}
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


async def test_no_calendar_plan_means_no_sequence(client, async_test_session):
    """DEV-6936: a housing nobody planned must not get a sequence from the default
    template — and rows created by the old fallback are purged on re-sync."""
    with patch("src.services.sync.service.ReportApi", return_value=_make_report_api_mock()):
        await _sync_tech_sequence_prerequisites(client)
        await client.post(f"{API}/sync/tech-sequence", params={"housing_raport_id": RAPORT_HOUSING_ID})

    no_plan = _make_report_api_mock(overrides={"has_calendar_plan": False})
    with patch("src.services.sync.service.ReportApi", return_value=no_plan):
        resp = await client.post(f"{API}/sync/tech-sequence", params={"housing_raport_id": RAPORT_HOUSING_ID})

    assert resp.status_code == 200
    assert resp.json()["data"]["tech_sequence"] == 0
    no_plan.list_plan_templates.assert_not_called()
    no_plan.get_plan_template_data.assert_not_called()

    from src.models import managers

    housing = (await managers.HousingManager(async_test_session).search(raport_id=RAPORT_HOUSING_ID))[0]
    remaining = await managers.TechSequenceItemManager(async_test_session).search(
        housing_id=housing.id, source="raport"
    )
    assert remaining == []


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
        "tech_sequence",
    }
    assert data["users"]["users"] == 1
    assert data["contractors"]["contractors"] == 1
    assert data["contracts"]["contracts"] == 1
    assert data["objects"]["projects"] == 1
    assert data["work_catalog"]["works"] == 2
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
