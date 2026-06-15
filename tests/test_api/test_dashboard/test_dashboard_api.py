import pytest

from tests.constants import API
from datetime import date, timedelta

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.smoke
async def test_dashboard_overview_returns_200(client):
    response = await client.get(f"{API}/dashboard/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    data = body["data"]
    assert "total_plan_items" in data
    assert "total_work_facts" in data
    assert "total_alerts" in data
    assert "date_from" in data
    assert "date_to" in data


async def test_dashboard_overview_with_housing_filter(client):
    response = await client.get(
        f"{API}/dashboard/overview",
        params={"housing_id": HOUSING_1_ID},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["housing_id"] == HOUSING_1_ID
    assert data["housing_name"] == "Корпус 1"


async def test_dashboard_overview_with_date_range(client):
    today = date.today()
    response = await client.get(
        f"{API}/dashboard/overview",
        params={
            "date_from": str(today - timedelta(days=30)),
            "date_to": str(today),
        },
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["date_from"] == str(today - timedelta(days=30))
    assert data["date_to"] == str(today)
    assert isinstance(data["total_plan_items"], int)
    assert isinstance(data["total_alerts"], int)


SECTION_1_ID = "33333333-3333-3333-3333-333333333333"


async def test_dashboard_overview_with_section_filter(client):
    response = await client.get(
        f"{API}/dashboard/overview",
        params={"housing_id": HOUSING_1_ID, "section_id": SECTION_1_ID},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["section_id"] == SECTION_1_ID
    assert data["section_name"] == "Секция 1"


async def test_dashboard_sections_breakdown(client):
    response = await client.get(
        f"{API}/dashboard/sections",
        params={"housing_id": HOUSING_1_ID},
    )

    assert response.status_code == 200
    rows = response.json()["data"]
    assert isinstance(rows, list)
    # Housing 1 has two sections in the fixtures.
    assert {r["section_name"] for r in rows} >= {"Секция 1", "Секция 2"}
    for r in rows:
        assert "total_plan_items" in r
        assert "completion_rate" in r


async def test_dashboard_sections_requires_housing_id(client):
    response = await client.get(f"{API}/dashboard/sections")
    assert response.status_code == 422
