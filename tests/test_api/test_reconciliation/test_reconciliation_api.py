import pytest
from datetime import date

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.smoke
async def test_list_reconciliation_results_returns_200(client):
    response = await client.get("/api/v1/reconciliation/results")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)


@pytest.mark.smoke
async def test_list_daily_summaries_returns_200(client):
    response = await client.get("/api/v1/reconciliation/summaries")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)


async def test_get_reconciliation_result_not_found_returns_404(client):
    response = await client.get("/api/v1/reconciliation/results/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


async def test_run_reconciliation_returns_200(client):
    response = await client.post(
        "/api/v1/reconciliation/run",
        json={"date": str(date.today()), "housing_id": HOUSING_1_ID},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert "total_results" in data
    assert "housing_count" in data
    assert data["housing_count"] == 1
