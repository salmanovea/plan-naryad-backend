from uuid import UUID

import pytest

from tests.constants import API
from datetime import date

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"
SECTION_1_ID = "33333333-3333-3333-3333-333333333333"
FLOOR_1_ID = "55555555-5555-5555-5555-555555555555"
WORK_1_ID = "88888888-8888-8888-8888-888888888888"
CONTRACTOR_1_ID = "99999999-9999-9999-9999-999999999999"


@pytest.fixture(autouse=True)
def _raport_stub(monkeypatch):
    """Manual creation validates the assignment against live Raport; stub it out.

    The contractor from the fixtures is treated as assigned everywhere, and the chessboard
    comes back empty — enough for the API-level checks in this module.
    """
    from src.services.contractor_works import HousingAssignments
    from src.services.contractor_works.service import ContractorWorksService
    from src.services.report_cells import HousingSlice
    from src.services.report_cells.service import ReportCellsService

    async def _contractors(self, work_id, floor_id):
        return [UUID(CONTRACTOR_1_ID)]

    async def _slice(self, housing_id, work_ids=None):
        return HousingSlice()

    async def _assignments(self, housing_id):
        return HousingAssignments()

    monkeypatch.setattr(ContractorWorksService, "get_contractors_for_cell", _contractors)
    monkeypatch.setattr(ContractorWorksService, "get_housing_assignments", _assignments)
    monkeypatch.setattr(ReportCellsService, "get_housing_slice", _slice)


@pytest.mark.smoke
async def test_list_plan_items_returns_200(client):
    response = await client.get(f"{API}/plan-naryad/")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)


async def test_get_daily_plan_returns_200(client):
    response = await client.get(
        f"{API}/plan-naryad/daily",
        params={"target_date": str(date.today()), "housing_id": HOUSING_1_ID},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["housing_id"] == HOUSING_1_ID
    assert isinstance(data["items"], list)


async def test_create_plan_item_returns_201(client):
    response = await client.post(
        f"{API}/plan-naryad/",
        json={
            "date": str(date.today()),
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID,
            "floor_id": FLOOR_1_ID,
            "work_id": WORK_1_ID,
            "contractor_id": CONTRACTOR_1_ID,
        },
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["data"]["housing_id"] == HOUSING_1_ID
    assert "planned_volume" not in body["data"]
    assert body["data"]["source"] == "manual"


async def test_get_plan_item_not_found_returns_404(client):
    response = await client.get(f"{API}/plan-naryad/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


async def test_list_plan_items_with_filters(client):
    response = await client.get(
        f"{API}/plan-naryad/",
        params={
            "housing_id": HOUSING_1_ID,
            "date_from": str(date.today()),
            "date_to": str(date.today()),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)
    for item in body["data"]:
        assert item["housing_id"] == HOUSING_1_ID


SECTION_1_ID = "33333333-3333-3333-3333-333333333333"


async def test_get_daily_plan_accepts_section_filter(client):
    response = await client.get(
        f"{API}/plan-naryad/daily",
        params={
            "target_date": str(date.today()),
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data["items"], list)
    for item in data["items"]:
        assert item["section_id"] == SECTION_1_ID


async def test_generate_plan_accepts_section(client):
    """A re-run has to say `force`, because it rebuilds the whole day."""
    response = await client.post(
        f"{API}/plan-naryad/generate",
        json={
            "date": str(date.today()),
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID,
            "force": True,
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert "count" in body["data"]


async def test_generate_plan_on_non_empty_day_asks_for_confirmation(client):
    """Positions already there → 409 with the warning text from the spec."""
    payload = {
        "date": str(date.today()),
        "housing_id": HOUSING_1_ID,
        "section_id": SECTION_1_ID,
    }
    await client.post(f"{API}/plan-naryad/", json={**payload, **_MANUAL_ITEM})

    response = await client.post(f"{API}/plan-naryad/generate", json=payload)

    assert response.status_code == 409
    assert "будет сформирован заново" in response.json()["message"]


_MANUAL_ITEM = {
    "floor_id": "55555555-5555-5555-5555-555555555555",
    "work_id": "88888888-8888-8888-8888-888888888888",
    "contractor_id": "99999999-9999-9999-9999-999999999999",
}


SECTION_1_ID_ENR = "33333333-3333-3333-3333-333333333333"
FLOOR_1_ID_ENR = "55555555-5555-5555-5555-555555555555"
WORK_ID_ENR = "88888888-8888-8888-8888-888888888888"
CONTRACTOR_ID_ENR = "99999999-9999-9999-9999-999999999999"


async def test_daily_plan_items_are_enriched(client):
    """daily plan items carry section/floor/contractor names (issue 11)."""
    enr_date = "2025-04-04"
    await client.post(
        f"{API}/plan-naryad/",
        json={
            "date": enr_date,
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID_ENR,
            "floor_id": FLOOR_1_ID_ENR,
            "work_id": WORK_ID_ENR,
            "contractor_id": CONTRACTOR_ID_ENR,
            "planned_volume": "7",
            "unit": "м3",
        },
    )
    resp = await client.get(
        f"{API}/plan-naryad/daily",
        params={"target_date": enr_date, "housing_id": HOUSING_1_ID, "section_id": SECTION_1_ID_ENR},
    )
    items = resp.json()["data"]["items"]
    assert items
    item = items[0]
    assert item["section_name"] == "Секция 1"
    assert item["floor_name"] == "Этаж 1"
    assert item["contractor_name"] == "ООО Стройтест"
