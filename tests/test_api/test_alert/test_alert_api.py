import pytest

from tests.constants import API
from datetime import date

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.smoke
async def test_list_alerts_returns_200(client):
    response = await client.get(f"{API}/alerts/")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert isinstance(body["data"], list)


async def test_get_alert_not_found_returns_404(client):
    response = await client.get(f"{API}/alerts/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


async def test_generate_alerts_returns_200(client):
    response = await client.post(
        f"{API}/alerts/generate",
        json={"housing_id": HOUSING_1_ID, "alert_date": str(date.today())},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert "generated" in data
    assert "alerts" in data
    assert isinstance(data["alerts"], list)


async def test_run_escalation_check_returns_200(client):
    response = await client.post(f"{API}/alerts/escalation/run")

    assert response.status_code == 200
    body = response.json()
    assert "escalated_count" in body["data"]
