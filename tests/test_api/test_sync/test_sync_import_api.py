"""
Tests for POST /api/v1/sync/import/* endpoints.

These don't talk to Raport — they accept payloads directly and exercise
the same upsert path as /sync/* (key=raport_id, ON CONFLICT DO UPDATE).
"""

import uuid

import pytest


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

    response = await client.post("/api/v1/sync/import/projects", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {"received": 1, "upserted": 1, "missing_parents": 0}

    from src.models import managers

    rows = await managers.WfProjectManager(async_test_session).search(raport_id=raport_id)
    assert len(rows) == 1
    assert rows[0].name == "ЖК Импорт"
    assert rows[0].project_class == "Бизнес"


async def test_import_projects_idempotent(client):
    raport_id = _id()
    payload = {"items": [{"raport_id": raport_id, "name": "A"}]}
    await client.post("/api/v1/sync/import/projects", json=payload)

    payload["items"][0]["name"] = "B"
    resp = await client.post("/api/v1/sync/import/projects", json=payload)

    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1


# ---------------------------------------------------------------------------
# import/construction-objects (parent: project)
# ---------------------------------------------------------------------------


async def test_import_construction_objects_resolves_parent(client, async_test_session):
    project_rid = _id()
    co_rid = _id()

    await client.post(
        "/api/v1/sync/import/projects",
        json={"items": [{"raport_id": project_rid, "name": "P"}]},
    )

    resp = await client.post(
        "/api/v1/sync/import/construction-objects",
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

    rows = await managers.WfProjectObjectManager(async_test_session).search(raport_id=co_rid)
    assert len(rows) == 1
    assert rows[0].name == "CO"


async def test_import_construction_objects_skips_missing_parent(client):
    resp = await client.post(
        "/api/v1/sync/import/construction-objects",
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
        "/api/v1/sync/import/projects",
        json={"items": [{"raport_id": project_rid, "name": "P"}]},
    )
    await client.post(
        "/api/v1/sync/import/construction-objects",
        json={"items": [{"raport_id": co_rid, "project_raport_id": project_rid, "name": "CO"}]},
    )

    resp = await client.post(
        "/api/v1/sync/import/housings",
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
        "/api/v1/sync/import/housings",
        json={"items": [{"raport_id": housing_rid, "name": "H", "complex_name": "ЖК"}]},
    )

    resp = await client.post(
        "/api/v1/sync/import/sections",
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
        "/api/v1/sync/import/floors",
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
    group_rid = _id()
    type_rid = _id()

    await client.post(
        "/api/v1/sync/import/work-groups",
        json={"items": [{"raport_id": group_rid, "name": "Монолит", "code": "MON"}]},
    )

    resp = await client.post(
        "/api/v1/sync/import/work-types",
        json={
            "items": [
                {
                    "raport_id": type_rid,
                    "work_group_raport_id": group_rid,
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
    assert types[0].unit == "м3"


# ---------------------------------------------------------------------------
# import/contractors
# ---------------------------------------------------------------------------


@pytest.mark.smoke
async def test_import_contractors_short_name_fallback(client, async_test_session):
    rid = _id()
    long_name = "Очень длинное название контрагента " + "x" * 200

    resp = await client.post(
        "/api/v1/sync/import/contractors",
        json={"items": [{"raport_id": rid, "name": long_name, "inn": "1234567890"}]},
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["upserted"] == 1

    from src.models import managers

    rows = await managers.ContractorManager(async_test_session).search(raport_id=rid)
    assert len(rows) == 1
    assert len(rows[0].short_name) <= 100
    assert rows[0].name == long_name
