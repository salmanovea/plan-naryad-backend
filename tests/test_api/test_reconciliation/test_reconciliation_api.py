import pytest

from tests.constants import API
from datetime import date

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.smoke
async def test_list_reconciliation_results_returns_200(client):
    response = await client.get(f"{API}/reconciliation/results")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)


@pytest.mark.smoke
async def test_list_daily_summaries_returns_200(client):
    response = await client.get(f"{API}/reconciliation/summaries")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)


async def test_get_reconciliation_result_not_found_returns_404(client):
    response = await client.get(f"{API}/reconciliation/results/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


async def test_run_reconciliation_returns_200(client):
    response = await client.post(
        f"{API}/reconciliation/run",
        json={"date": str(date.today()), "housing_id": HOUSING_1_ID},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert "total_results" in data
    assert "housing_count" in data
    assert data["housing_count"] == 1


SECTION_1_ID = "33333333-3333-3333-3333-333333333333"
FLOOR_1_ID = "55555555-5555-5555-5555-555555555555"
WORK_TYPE_ID = "88888888-8888-8888-8888-888888888888"
CONTRACTOR_ID = "99999999-9999-9999-9999-999999999999"
RECON_DATE = "2025-03-03"


async def _seed_plan_and_fact(client):
    """Create a matching plan item (100) and fact (85) for RECON_DATE."""
    await client.post(
        f"{API}/plan-naryad/",
        json={
            "date": RECON_DATE,
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID,
            "floor_id": FLOOR_1_ID,
            "work_type_id": WORK_TYPE_ID,
            "contractor_id": CONTRACTOR_ID,
            "planned_volume": "100",
            "unit": "м3",
        },
    )
    await client.post(
        f"{API}/work-facts/",
        json={
            "date": RECON_DATE,
            "housing_id": HOUSING_1_ID,
            "section_id": SECTION_1_ID,
            "floor_id": FLOOR_1_ID,
            "work_type_id": WORK_TYPE_ID,
            "contractor_id": CONTRACTOR_ID,
            "actual_volume": "85",
            "unit": "м3",
        },
    )


async def test_reconciliation_run_is_idempotent(client):
    await _seed_plan_and_fact(client)

    first = await client.post(f"{API}/reconciliation/run", json={"date": RECON_DATE, "housing_id": HOUSING_1_ID})
    second = await client.post(f"{API}/reconciliation/run", json={"date": RECON_DATE, "housing_id": HOUSING_1_ID})
    assert first.status_code == 200
    assert second.status_code == 200

    # A second run must replace, not duplicate, the rows for that (date, housing).
    assert second.json()["data"]["total_results"] == first.json()["data"]["total_results"]

    results = await client.get(f"{API}/reconciliation/results", params={"date_from": RECON_DATE, "date_to": RECON_DATE})
    rows = results.json()["data"]
    assert len(rows) == 1

    summaries = await client.get(
        f"{API}/reconciliation/summaries", params={"date_from": RECON_DATE, "date_to": RECON_DATE}
    )
    assert len(summaries.json()["data"]) == 1


async def test_reconciliation_result_is_enriched_and_scaled(client):
    await _seed_plan_and_fact(client)
    await client.post(f"{API}/reconciliation/run", json={"date": RECON_DATE, "housing_id": HOUSING_1_ID})

    results = await client.get(f"{API}/reconciliation/results", params={"date_from": RECON_DATE, "date_to": RECON_DATE})
    row = results.json()["data"][0]

    # Issue 8: labels are always present (no bare dash in the UI).
    assert row["floor_name"] == "Этаж 1"
    assert row["section_name"] == "Секция 1"
    assert row["floor_number"] == 1

    # Issue 6: completion_ratio is a 0..1 fraction (85 / 100 = 0.85).
    assert abs(float(row["completion_ratio"]) - 0.85) < 0.01

    summaries = await client.get(
        f"{API}/reconciliation/summaries", params={"date_from": RECON_DATE, "date_to": RECON_DATE}
    )
    summary = summaries.json()["data"][0]
    # Summary rates share the 0..1 scale (never 0..100).
    assert 0 <= float(summary["completion_rate"]) <= 1
    assert 0 <= float(summary["submission_rate"]) <= 1
