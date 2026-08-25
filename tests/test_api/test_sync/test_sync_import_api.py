"""
Tests for POST /api/v1/sync/import/* endpoints.

These don't talk to Raport — they accept payloads directly and exercise
the same upsert path as /sync/* (key=raport_id, ON CONFLICT DO UPDATE).
"""

import uuid

import pytest

from tests.constants import API


def _id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# import/projects
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_import_projects_upserts(client, async_test_session):
    raport_id = _id()
    payload = {
        "items": [
            {
                "raport_id": raport_id,
                "name": "ЖК Импорт",
                "project_class": "Бизнес",
                "description": "from xlsx",
            }
        ]
    }

    response = await client.post(f"{API}/sync/import/projects", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {"received": 1, "upserted": 1, "missing_parents": 0}

    from src.models import managers

    rows = await managers.ProjectManager(async_test_session).search(raport_id=raport_id)
    assert len(rows) == 1
    assert rows[0].name == "ЖК Импорт"
    assert rows[0].project_class == "Бизнес"


async def test_import_projects_idempotent(client):
    raport_id = _id()
    payload = {"items": [{"raport_id": raport_id, "name": "A"}]}
    await client.post(f"{API}/sync/import/projects", json=payload)

    payload["items"][0]["name"] = "B"
    resp = await client.post(f"{API}/sync/import/projects", json=payload)

    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1


# ---------------------------------------------------------------------------
# import/construction-objects (parent: project)
# ---------------------------------------------------------------------------


async def test_import_construction_objects_resolves_parent(client, async_test_session):
    project_rid = _id()
    co_rid = _id()

    await client.post(
        f"{API}/sync/import/projects",
        json={"items": [{"raport_id": project_rid, "name": "P"}]},
    )

    resp = await client.post(
        f"{API}/sync/import/construction-objects",
        json={
            "items": [
                {
                    "raport_id": co_rid,
                    "project_raport_id": project_rid,
                    "name": "CO",
                }
            ]
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"received": 1, "upserted": 1, "missing_parents": 0}

    from src.models import managers

    rows = await managers.ConstructionObjectManager(async_test_session).search(raport_id=co_rid)
    assert len(rows) == 1
    assert rows[0].name == "CO"


async def test_import_construction_objects_skips_missing_parent(client):
    resp = await client.post(
        f"{API}/sync/import/construction-objects",
        json={
            "items": [
                {
                    "raport_id": _id(),
                    "project_raport_id": _id(),  # non-existent
                    "name": "Orphan",
                }
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == {"received": 1, "upserted": 0, "missing_parents": 1}


# ---------------------------------------------------------------------------
# import/housings (parent: construction-object, optional)
# ---------------------------------------------------------------------------


async def test_import_housings_with_and_without_parent(client, async_test_session):
    project_rid = _id()
    co_rid = _id()
    housing_with_parent = _id()
    housing_no_parent = _id()

    await client.post(
        f"{API}/sync/import/projects",
        json={"items": [{"raport_id": project_rid, "name": "P"}]},
    )
    await client.post(
        f"{API}/sync/import/construction-objects",
        json={"items": [{"raport_id": co_rid, "project_raport_id": project_rid, "name": "CO"}]},
    )

    resp = await client.post(
        f"{API}/sync/import/housings",
        json={
            "items": [
                {
                    "raport_id": housing_with_parent,
                    "name": "H1",
                    "complex_name": "ЖК",
                    "construction_object_raport_id": co_rid,
                },
                {
                    "raport_id": housing_no_parent,
                    "name": "H2",
                    "complex_name": "ЖК",
                },
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 2

    from src.models import managers

    h1 = await managers.HousingManager(async_test_session).search(raport_id=housing_with_parent)
    assert len(h1) == 1
    assert h1[0].construction_object_id is not None

    h2 = await managers.HousingManager(async_test_session).search(raport_id=housing_no_parent)
    assert len(h2) == 1
    assert h2[0].construction_object_id is None


# ---------------------------------------------------------------------------
# import/sections (parent: housing) and import/floors (parent: section)
# ---------------------------------------------------------------------------


async def test_import_sections_and_floors_chain(client, async_test_session):
    housing_rid = _id()
    section_rid = _id()
    floor_rid = _id()

    await client.post(
        f"{API}/sync/import/housings",
        json={"items": [{"raport_id": housing_rid, "name": "H", "complex_name": "ЖК"}]},
    )

    resp = await client.post(
        f"{API}/sync/import/sections",
        json={
            "items": [
                {
                    "raport_id": section_rid,
                    "housing_raport_id": housing_rid,
                    "name": "Весь корпус",
                    "section_number": 0,
                }
            ]
        },
    )
    assert resp.json()["data"]["upserted"] == 1

    resp = await client.post(
        f"{API}/sync/import/floors",
        json={
            "items": [
                {
                    "raport_id": floor_rid,
                    "section_raport_id": section_rid,
                    "name": "ФП",
                    "floor_number": 0,
                }
            ]
        },
    )
    assert resp.json()["data"]["upserted"] == 1

    from src.models import managers

    floors = await managers.FloorManager(async_test_session).search(raport_id=floor_rid)
    assert len(floors) == 1
    assert floors[0].name == "ФП"


# ---------------------------------------------------------------------------
# import/work-groups + import/work-types
# ---------------------------------------------------------------------------


async def test_import_work_catalog_chain(client, async_test_session):
    """work_type («Вид работ») then work («Работа») nested under it."""
    type_rid = _id()
    work_rid = _id()

    resp = await client.post(
        f"{API}/sync/import/work-types",
        json={"items": [{"raport_id": type_rid, "name": "Монолит", "code": "MON"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1

    resp = await client.post(
        f"{API}/sync/import/works",
        json={
            "items": [
                {
                    "raport_id": work_rid,
                    "work_type_raport_id": type_rid,
                    "name": "Заливка",
                    "code": "POUR",
                    "unit": "м3",
                }
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1

    from src.models import managers

    types = await managers.WorkTypeManager(async_test_session).search(raport_id=type_rid)
    assert len(types) == 1

    works = await managers.WorkManager(async_test_session).search(raport_id=work_rid)
    assert len(works) == 1
    assert works[0].unit == "м3"
    assert works[0].work_type_id == types[0].id


# ---------------------------------------------------------------------------
# import/contractors
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_import_contractors_short_name_fallback(client, async_test_session):
    rid = _id()
    long_name = "Очень длинное название контрагента " + "x" * 200

    resp = await client.post(
        f"{API}/sync/import/contractors",
        json={"items": [{"raport_id": rid, "name": long_name, "inn": "1234567890"}]},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1

    from src.models import managers

    rows = await managers.ContractorManager(async_test_session).search(raport_id=rid)
    assert len(rows) == 1
    assert len(rows[0].short_name) <= 100
    assert rows[0].name == long_name


# ---------------------------------------------------------------------------
# import/users
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_import_users_upserts(client, async_test_session):
    user_rid = _id()
    resp = await client.post(
        f"{API}/sync/import/users",
        json={
            "items": [
                {
                    "raport_id": user_rid,
                    "shown_name": "Петров Пётр",
                    "email": "petrov@fsk.ru",
                    "is_external": False,
                    "groups": ["controller"],
                    "project_ids": [_id()],
                }
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1

    from src.models import managers

    rows = await managers.UserManager(async_test_session).search(raport_id=user_rid)
    assert len(rows) == 1
    assert rows[0].shown_name == "Петров Пётр"
    assert rows[0].groups == ["controller"]
    assert len(rows[0].project_ids) == 1


# ---------------------------------------------------------------------------
# import/contracts (parent: contractor, optional)
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_import_contracts_resolves_contractor(client, async_test_session):
    contractor_rid, contract_rid = _id(), _id()
    await client.post(
        f"{API}/sync/import/contractors",
        json={"items": [{"raport_id": contractor_rid, "name": "Подрядчик Д"}]},
    )

    resp = await client.post(
        f"{API}/sync/import/contracts",
        json={
            "items": [
                {
                    "raport_id": contract_rid,
                    "contractor_raport_id": contractor_rid,
                    "name": "Договор №7",
                    "subject": "Предмет договора",
                    "is_warranty_letter": True,
                }
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1

    from src.models import managers

    contractor = (await managers.ContractorManager(async_test_session).search(raport_id=contractor_rid))[0]
    rows = await managers.ContractManager(async_test_session).search(raport_id=contract_rid)
    assert len(rows) == 1
    assert rows[0].subject == "Предмет договора"
    assert rows[0].is_warranty_letter is True
    assert rows[0].contractor_id == contractor.id


async def test_import_contracts_unknown_contractor_stored_with_null(client, async_test_session):
    """A contract referencing an unsynced contractor is stored with a null contractor."""
    contract_rid = _id()
    resp = await client.post(
        f"{API}/sync/import/contracts",
        json={"items": [{"raport_id": contract_rid, "contractor_raport_id": _id(), "subject": "Без подрядчика"}]},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1

    from src.models import managers

    rows = await managers.ContractManager(async_test_session).search(raport_id=contract_rid)
    assert len(rows) == 1
    assert rows[0].contractor_id is None


# ---------------------------------------------------------------------------
# unified POST /sync/import (enum dispatcher)
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_import_all_processes_all_provided_lists(client, async_test_session):
    """No `entities` → every provided payload list is processed; parent→child order resolves FKs."""
    project_rid, co_rid, contractor_rid = _id(), _id(), _id()
    body = {
        "contractors": [{"raport_id": contractor_rid, "name": "Подрядчик X"}],
        "projects": [{"raport_id": project_rid, "name": "ЖК Unified"}],
        "construction_objects": [{"raport_id": co_rid, "project_raport_id": project_rid, "name": "ОС 1"}],
    }

    resp = await client.post(f"{API}/sync/import", json=body)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"contractors", "projects", "construction_objects"}
    # construction object resolved its parent project despite being in the same call
    assert data["construction_objects"] == {"received": 1, "upserted": 1, "missing_parents": 0}

    from src.models import managers

    assert len(await managers.ConstructionObjectManager(async_test_session).search(raport_id=co_rid)) == 1


async def test_import_all_entities_filter(client, async_test_session):
    """`entities` selects which provided lists run; others are ignored."""
    project_rid, contractor_rid = _id(), _id()
    body = {
        "entities": ["projects"],
        "projects": [{"raport_id": project_rid, "name": "Только проект"}],
        "contractors": [{"raport_id": contractor_rid, "name": "Игнор"}],
    }

    resp = await client.post(f"{API}/sync/import", json=body)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"projects"}

    from src.models import managers

    assert await managers.ContractorManager(async_test_session).search(raport_id=contractor_rid) == []
