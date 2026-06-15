import uuid
from datetime import date, datetime, timedelta

import pytest

from src.models.dbo.tables.alert import Alert
from tests.constants import API

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


async def test_escalation_raises_level_for_aged_alert(client, async_test_session):
    """An unacknowledged A05 alert older than its SLA must escalate (issue 1)."""
    alert_id = uuid.uuid4()
    aged = Alert(
        id=alert_id,
        alert_type="A05",
        level="warning",
        date=date.today(),
        housing_id=uuid.UUID(HOUSING_1_ID),
        recipient_role="RS",
        message="aged alert",
        acknowledged=False,
        escalation_level=1,
        created_at=datetime.now() - timedelta(hours=10),
    )
    async_test_session.add(aged)
    await async_test_session.commit()

    try:
        response = await client.post(f"{API}/alerts/escalation/run")
        assert response.status_code == 200
        assert response.json()["data"]["escalated_count"] >= 1

        detail = await client.get(f"{API}/alerts/{alert_id}")
        data = detail.json()["data"]
        # A05 escalates RS (level 1) -> DS (level 2) after 8h.
        assert data["escalation_level"] == 2
        assert data["recipient_role"] == "DS"
    finally:
        await async_test_session.delete(aged)
        await async_test_session.commit()


async def test_alert_list_has_enriched_housing_name(client):
    """housing_name must be denormalized in the list response (issue 10)."""
    await client.post(
        f"{API}/alerts/generate",
        json={"housing_id": HOUSING_1_ID, "alert_date": str(date.today())},
    )
    resp = await client.get(f"{API}/alerts/", params={"housing_id": HOUSING_1_ID})
    rows = resp.json()["data"]
    assert rows
    assert all(r["housing_id"] == HOUSING_1_ID for r in rows)
    assert any(r["housing_name"] for r in rows)
