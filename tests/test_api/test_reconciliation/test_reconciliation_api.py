from uuid import UUID

import pytest

from tests.constants import API
from datetime import date

HOUSING_1_ID = "11111111-1111-1111-1111-111111111111"


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
        return [UUID(CONTRACTOR_ID)]

    async def _slice(self, housing_id, work_ids=None):
        return HousingSlice()

    async def _assignments(self, housing_id):
        return HousingAssignments()

    monkeypatch.setattr(ContractorWorksService, "get_contractors_for_cell", _contractors)
    monkeypatch.setattr(ContractorWorksService, "get_housing_assignments", _assignments)
    monkeypatch.setattr(ReportCellsService, "get_housing_slice", _slice)


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
        json={"date_from": str(date.today()), "housing_id": HOUSING_1_ID},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert "total_results" in data
    assert "housing_count" in data
    assert data["housing_count"] == 1


SECTION_1_ID = "33333333-3333-3333-3333-333333333333"
FLOOR_1_ID = "55555555-5555-5555-5555-555555555555"
WORK_ID = "88888888-8888-8888-8888-888888888888"
CONTRACTOR_ID = "99999999-9999-9999-9999-999999999999"
RECON_DATE = "2025-03-03"


async def _seed_plan_and_fact(client):
    """A matching plan item (100) and fact (85) for RECON_DATE.

    Both go straight through the managers: the API no longer accepts a volume on a position
    (Р6) and never accepted facts at all, but the volume columns are still what
    `classify_status` reads until stage 7 moves it onto percents.
    """
    from src.config.postgres.db_config import get_async_session
    from src.models import managers

    async with get_async_session() as db:
        plans = managers.PlanItemManager(db)
        if not await plans.search(date=date.fromisoformat(RECON_DATE), housing_id=HOUSING_1_ID):
            await plans.create(
                {
                    "date": date.fromisoformat(RECON_DATE),
                    "housing_id": HOUSING_1_ID,
                    "section_id": SECTION_1_ID,
                    "floor_id": FLOOR_1_ID,
                    "work_id": WORK_ID,
                    "contractor_id": CONTRACTOR_ID,
                    "source_percent": "20",
                    "source": "auto",
                    "status": "draft",
                }
            )

        facts = managers.WorkFactManager(db)
        if not await facts.search(raport_id="bbbb1111-0000-0000-0000-000000000001"):
            await facts.create(
                {
                    "raport_id": "bbbb1111-0000-0000-0000-000000000001",
                    "work_date": date.fromisoformat(RECON_DATE),
                    "housing_id": HOUSING_1_ID,
                    "section_id": SECTION_1_ID,
                    "floor_id": FLOOR_1_ID,
                    "work_id": WORK_ID,
                    "contractor_id": CONTRACTOR_ID,
                    "volume": "85",
                    "unit": "м3",
                    "source": "raport",
                }
            )


async def test_reconciliation_run_is_idempotent(client):
    await _seed_plan_and_fact(client)

    first = await client.post(
        f"{API}/reconciliation/run", json={"date_from": RECON_DATE, "date_to": RECON_DATE, "housing_id": HOUSING_1_ID}
    )
    second = await client.post(
        f"{API}/reconciliation/run", json={"date_from": RECON_DATE, "date_to": RECON_DATE, "housing_id": HOUSING_1_ID}
    )
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
    await client.post(
        f"{API}/reconciliation/run", json={"date_from": RECON_DATE, "date_to": RECON_DATE, "housing_id": HOUSING_1_ID}
    )

    results = await client.get(f"{API}/reconciliation/results", params={"date_from": RECON_DATE, "date_to": RECON_DATE})
    row = results.json()["data"][0]

    # Issue 8: labels are always present (no bare dash in the UI).
    assert row["floor_name"] == "Этаж 1"
    assert row["section_name"] == "Секция 1"
    assert row["floor_number"] == 1

    # Percents replaced volumes (Р6c): «% Исходный» is the snapshot from the position,
    # «% Факт» comes from the chessboard — empty here, so the row is NOT_DONE at 0.
    assert row["source_percent"] == "20.00"
    assert "planned_volume" not in row
    assert row["status"] in {"NOT_DONE", "NO_REPORT"}

    summaries = await client.get(
        f"{API}/reconciliation/summaries", params={"date_from": RECON_DATE, "date_to": RECON_DATE}
    )
    summary = summaries.json()["data"][0]
    # Summary rates share the 0..1 scale (never 0..100).
    assert 0 <= float(summary["completion_rate"]) <= 1
    assert 0 <= float(summary["submission_rate"]) <= 1


async def test_filter_options_list_only_what_the_scope_contains(client):
    """Column filters are built on the server: the table is paginated, the page is not the scope."""
    await _seed_plan_and_fact(client)
    await client.post(
        f"{API}/reconciliation/run", json={"date_from": RECON_DATE, "date_to": RECON_DATE, "housing_id": HOUSING_1_ID}
    )

    response = await client.get(
        f"{API}/reconciliation/filter-options",
        params={"housing_id": HOUSING_1_ID, "date_from": RECON_DATE, "date_to": RECON_DATE},
    )
    options = response.json()["data"]

    assert response.status_code == 200
    assert [s["id"] for s in options["sections"]] == [SECTION_1_ID]
    assert [f["id"] for f in options["floors"]] == [FLOOR_1_ID]
    # The floor knows its section — the filter is a «Секция → Этаж» tree.
    assert options["floors"][0]["section_id"] == SECTION_1_ID
    assert [w["id"] for w in options["works"]] == [WORK_ID]
    assert [c["id"] for c in options["contractors"]] == [CONTRACTOR_ID]
    assert options["statuses"]


async def test_filter_options_are_empty_outside_the_reconciled_range(client):
    response = await client.get(
        f"{API}/reconciliation/filter-options",
        params={"housing_id": HOUSING_1_ID, "date_from": "2000-01-01", "date_to": "2000-01-02"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "statuses": [],
        "patterns": [],
        "works": [],
        "sections": [],
        "floors": [],
        "contractors": [],
    }
