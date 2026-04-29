import pytest
from datetime import date

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"
SECTION_1_ID = "33333333-3333-3333-3333-333333333333"
FLOOR_1_ID = "55555555-5555-5555-5555-555555555555"
WORK_TYPE_1_ID = "88888888-8888-8888-8888-888888888888"
CONTRACTOR_1_ID = "99999999-9999-9999-9999-999999999999"


@pytest.mark.smoke
async def test_list_work_facts_returns_200(client):
    response = await client.get("/api/v1/work-facts/")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)


async def test_get_work_fact_not_found_returns_404(client):
    response = await client.get("/api/v1/work-facts/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


async def test_create_work_fact_returns_201(client):
    response = await client.post(
        "/api/v1/work-facts/",
        json={
            "date": str(date.today()),
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID,
            "floor_id": FLOOR_1_ID,
            "work_type_id": WORK_TYPE_1_ID,
            "contractor_id": CONTRACTOR_1_ID,
            "actual_volume": "10.5",
            "unit": "м3",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["housing_id"] == HOUSING_1_ID
    assert body["data"]["actual_volume"] == "10.5000"


async def test_list_work_facts_with_date_filter(client):
    response = await client.get(
        "/api/v1/work-facts/",
        params={"date_from": str(date.today()), "date_to": str(date.today())},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)
