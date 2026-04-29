import pytest

GROUP_1_ID = "77777777-7777-7777-7777-777777777777"
WORK_TYPE_1_ID = "88888888-8888-8888-8888-888888888888"
HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.smoke
async def test_list_work_groups_returns_200(client):
    response = await client.get("/api/v1/works/groups")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 1


async def test_get_work_group_by_id_returns_200(client):
    response = await client.get(f"/api/v1/works/groups/{GROUP_1_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == GROUP_1_ID
    assert body["data"]["code"] == "SMR"


async def test_get_work_group_not_found_returns_404(client):
    response = await client.get("/api/v1/works/groups/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


@pytest.mark.smoke
async def test_list_work_types_returns_200(client):
    response = await client.get("/api/v1/works/types")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 2


async def test_get_work_type_by_id_returns_200(client):
    response = await client.get(f"/api/v1/works/types/{WORK_TYPE_1_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == WORK_TYPE_1_ID
    assert body["data"]["code"] == "MONOLITH"
    assert body["data"]["unit"] == "м3"


async def test_create_work_group_returns_201(client):
    response = await client.post(
        "/api/v1/works/groups",
        json={"name": "Отделка", "code": "FINISH", "order": 2},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["code"] == "FINISH"


async def test_create_work_type_returns_201(client):
    response = await client.post(
        "/api/v1/works/types",
        json={
            "group_id": GROUP_1_ID,
            "name": "Арматура",
            "code": "REBAR_NEW",
            "unit": "т",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["code"] == "REBAR_NEW"
    assert body["data"]["group_id"] == GROUP_1_ID
