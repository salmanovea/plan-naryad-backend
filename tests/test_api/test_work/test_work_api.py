import pytest

from tests.constants import API

# The catalogue mirrors Raport: work_set → work_group → work_type → work.
# Fixtures hold one work_type («СМР») and two works under it.
WORK_TYPE_1_ID = "77777777-7777-7777-7777-777777777777"
WORK_1_ID = "88888888-8888-8888-8888-888888888888"
HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.smoke
async def test_list_work_groups_returns_200(client):
    response = await client.get(f"{API}/works/groups")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)


@pytest.mark.smoke
async def test_list_work_sets_returns_200(client):
    response = await client.get(f"{API}/works/sets")

    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


@pytest.mark.smoke
async def test_list_work_types_returns_200(client):
    response = await client.get(f"{API}/works/types")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 1


async def test_get_work_type_by_id_returns_200(client):
    response = await client.get(f"{API}/works/types/{WORK_TYPE_1_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == WORK_TYPE_1_ID
    assert body["data"]["code"] == "SMR"


async def test_get_work_type_not_found_returns_404(client):
    response = await client.get(f"{API}/works/types/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


@pytest.mark.smoke
async def test_list_works_returns_200(client):
    response = await client.get(f"{API}/works/")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 2


async def test_get_work_by_id_returns_200(client):
    response = await client.get(f"{API}/works/{WORK_1_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == WORK_1_ID
    assert body["data"]["code"] == "MONOLITH"
    assert body["data"]["unit"] == "м3"


async def test_create_work_group_returns_201(client):
    response = await client.post(
        f"{API}/works/groups",
        json={"name": "Отделка", "code": "FINISH", "order": 2},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["code"] == "FINISH"


async def test_create_work_returns_201(client):
    response = await client.post(
        f"{API}/works/",
        json={
            "work_type_id": WORK_TYPE_1_ID,
            "name": "Арматура",
            "code": "REBAR_NEW",
            "unit": "т",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["code"] == "REBAR_NEW"
    assert body["data"]["work_type_id"] == WORK_TYPE_1_ID


async def test_get_tech_sequence_returns_200(client):
    response = await client.get(f"{API}/works/tech-sequence/{HOUSING_1_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["housing_id"] == HOUSING_1_ID
    assert isinstance(body["data"]["sequence"], list)
