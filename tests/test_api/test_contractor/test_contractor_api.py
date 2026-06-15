import pytest

from tests.constants import API

CONTRACTOR_1_ID = "99999999-9999-9999-9999-999999999999"
CONTRACTOR_2_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.smoke
async def test_list_contractors_returns_200(client):
    response = await client.get(f"{API}/contractors/")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 2


async def test_get_contractor_by_id_returns_200(client):
    response = await client.get(f"{API}/contractors/{CONTRACTOR_1_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == CONTRACTOR_1_ID
    assert body["data"]["name"] == "ООО Стройтест"
    assert body["data"]["inn"] == "1234567890"


async def test_get_contractor_not_found_returns_404(client):
    response = await client.get(f"{API}/contractors/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


async def test_create_contractor_returns_201(client):
    response = await client.post(
        f"{API}/contractors/",
        json={"name": "ООО Новый", "short_name": "Новый"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["name"] == "ООО Новый"
    assert "id" in body["data"]


async def test_update_contractor_returns_200(client):
    response = await client.put(
        f"{API}/contractors/{CONTRACTOR_2_ID}",
        json={"contact_person": "Петров П.П."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["contact_person"] == "Петров П.П."


async def test_list_assignments_returns_200(client):
    response = await client.get(f"{API}/contractors/{HOUSING_1_ID}/assignments")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["housing_id"] == HOUSING_1_ID
    assert isinstance(body["data"]["assignments"], list)
