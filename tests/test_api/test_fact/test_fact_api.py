import pytest

from tests.constants import API
from datetime import date

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"
SECTION_1_ID = "33333333-3333-3333-3333-333333333333"
FLOOR_1_ID = "55555555-5555-5555-5555-555555555555"
WORK_1_ID = "88888888-8888-8888-8888-888888888888"
CONTRACTOR_1_ID = "99999999-9999-9999-9999-999999999999"


@pytest.mark.smoke
async def test_list_work_facts_returns_200(client):
    response = await client.get(f"{API}/work-facts/")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)


async def test_get_work_fact_not_found_returns_404(client):
    response = await client.get(f"{API}/work-facts/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


async def test_writing_facts_is_not_allowed(client):
    """Facts are entered in Raport only — the spec forbids creating them here."""
    payload = {
        "work_date": str(date.today()),
        "housing_id": HOUSING_1_ID,
        "section_id": SECTION_1_ID,
        "floor_id": FLOOR_1_ID,
        "work_id": WORK_1_ID,
        "contractor_id": CONTRACTOR_1_ID,
        "volume": "10.5",
    }

    created = await client.post(f"{API}/work-facts/", json=payload)
    updated = await client.put(f"{API}/work-facts/{WORK_1_ID}", json={"volume": "1"})
    deleted = await client.delete(f"{API}/work-facts/{WORK_1_ID}")

    assert created.status_code == 405
    assert updated.status_code == 405
    assert deleted.status_code == 405


async def test_fact_response_hides_volume_but_shows_percent(client, async_test_session):
    """Volumes stay in the DB but out of the API (Р6); percent is the real payload."""
    from src.models import managers

    fact = await managers.WorkFactManager(async_test_session).create(
        {
            "raport_id": "aaaa1111-0000-0000-0000-000000000001",
            "work_date": date.today(),
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID,
            "floor_id": FLOOR_1_ID,
            "work_id": WORK_1_ID,
            "contractor_id": CONTRACTOR_1_ID,
            "volume": 0,
            "percent": "42.5",
            "unit": "м3",
            "source": "raport",
        }
    )

    response = await client.get(f"{API}/work-facts/{fact.id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["percent"] == "42.50"
    assert "volume" not in data


async def test_fact_without_contractor_is_stored(client, async_test_session):
    """Raport leaves the contractor empty on most facts; the row must survive anyway."""
    from src.models import managers

    fact = await managers.WorkFactManager(async_test_session).create(
        {
            "raport_id": "aaaa1111-0000-0000-0000-000000000002",
            "work_date": date.today(),
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID,
            "floor_id": FLOOR_1_ID,
            "work_id": WORK_1_ID,
            "contractor_id": None,
            "volume": 0,
            "percent": "10",
            "source": "raport",
        }
    )

    response = await client.get(f"{API}/work-facts/{fact.id}")

    assert response.status_code == 200
    assert response.json()["data"]["contractor_id"] is None


async def test_list_work_facts_with_date_filter(client):
    response = await client.get(
        f"{API}/work-facts/",
        params={"date_from": str(date.today()), "date_to": str(date.today())},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)
