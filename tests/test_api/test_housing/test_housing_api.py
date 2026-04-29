import pytest

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"
HOUSING_2_ID = "22222222-2222-2222-2222-222222222222"
SECTION_1_ID = "33333333-3333-3333-3333-333333333333"


@pytest.mark.smoke
async def test_list_housings_returns_200(client):
    response = await client.get("/api/v1/housings/")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 2


async def test_get_housing_by_id_returns_200(client):
    response = await client.get(f"/api/v1/housings/{HOUSING_1_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["id"] == HOUSING_1_ID
    assert body["data"]["name"] == "Корпус 1"
    assert body["data"]["complex_name"] == "ЖК Тестовый"


async def test_get_housing_not_found_returns_404(client):
    response = await client.get("/api/v1/housings/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "404"


async def test_get_housing_structure_returns_200(client):
    response = await client.get(f"/api/v1/housings/{HOUSING_1_ID}/structure")

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["housing_id"] == HOUSING_1_ID
    assert data["housing_name"] == "Корпус 1"
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) == 2
    section = data["sections"][0]
    assert "section_id" in section
    assert "floors" in section


async def test_create_housing_returns_201(client):
    response = await client.post(
        "/api/v1/housings/",
        json={"name": "Новый корпус", "complex_name": "ЖК Новый"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["name"] == "Новый корпус"
    assert body["data"]["complex_name"] == "ЖК Новый"
    assert "id" in body["data"]


async def test_update_housing_returns_200(client):
    response = await client.put(
        f"/api/v1/housings/{HOUSING_2_ID}",
        json={"description": "Обновлённое описание"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["description"] == "Обновлённое описание"


async def test_list_sections_returns_200(client):
    response = await client.get(f"/api/v1/housings/{HOUSING_1_ID}/sections")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 2


async def test_list_floors_returns_200(client):
    response = await client.get(f"/api/v1/housings/sections/{SECTION_1_ID}/floors")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 2
