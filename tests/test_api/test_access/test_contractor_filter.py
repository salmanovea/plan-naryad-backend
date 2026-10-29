"""The page-level «Подрядчик» selector, forced to their own companies for external users.

Registered API + real PostgreSQL with synthetic profiles (see `tests/fixtures/access.py`).
Housing 0 is given rows of a second contractor so that narrowing is visible.
"""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from src.middlewares.raport_auth.backend import RaportUser
from src.models.dbo import models as m
from src.services.access.schemes import AccessScope, PlanRole
from src.services.contractor_works.service import ContractorWorksService
from tests.constants import API
from tests.fixtures.access import DAY, profile

SUMMARY_DAY = DAY + timedelta(days=1)
LONE_DAY = DAY + timedelta(days=2)


def _stats(total: int, done_full: int = 0, no_report: int = 0, unplanned: int = 0, percents: str = "0") -> dict:
    return {
        "total": total,
        "done_full": done_full,
        "done_partial": 0,
        "done_over": 0,
        "not_done": 0,
        "no_report": no_report,
        "unplanned": unplanned,
        "fact_percent_sum": percents,
        "fact_percent_count": total - unplanned - no_report,
    }


@pytest.fixture
async def two_contractors(access_data):
    """Rows of contractor 1 next to contractor 0's in housing 0, plus per-contractor summaries."""
    db, house, section, floor = (
        access_data.db,
        access_data.housings[0],
        access_data.sections[0],
        access_data.floors[0],
    )
    first, second = access_data.contractors[0], access_data.contractors[1]
    place = {"housing_id": house.id, "section_id": section.id, "floor_id": floor.id, "work_id": access_data.work.id}
    db.add_all(
        [
            m.WorkFact(work_date=DAY, contractor_id=second.id, volume=0, **place),
            m.ReconciliationResult(date=DAY, contractor_id=second.id, status="UNPLANNED", **place),
            m.Alert(
                date=DAY,
                housing_id=house.id,
                recipient_role="RS",
                alert_type="A01",
                message="Second contractor alert",
                level="info",
                contractor_id=second.id,
            ),
            m.DailySummary(
                date=SUMMARY_DAY,
                housing_id=house.id,
                total_planned=3,
                total_done_full=2,
                total_no_report=1,
                total_unplanned=1,
                contractor_details={
                    str(first.id): _stats(2, done_full=1, no_report=1),
                    str(second.id): _stats(2, done_full=1, unplanned=1, percents="100"),
                },
            ),
            m.DailySummary(
                date=LONE_DAY,
                housing_id=house.id,
                total_planned=1,
                contractor_details={str(second.id): _stats(1)},
            ),
        ]
    )
    await db.commit()
    return access_data


def _external(data, contractors=None) -> RaportUser:
    user = profile(data, contractors=contractors)
    user.data["is_external"] = True
    return user


# ── Policy ────────────────────────────────────────────────────────────────────


def test_is_external_comes_from_the_raport_profile():
    assert AccessScope.from_user(RaportUser({"groups": ["factgathering_user"], "is_external": True})).is_external
    assert not AccessScope.from_user(RaportUser({"groups": ["factgathering_user"]})).is_external


def test_external_superuser_is_not_narrowed():
    """Raport exempts superusers from the external-user filter; so do we."""
    scope = AccessScope.from_user(RaportUser({"groups": ["superuser"], "is_external": True}))
    assert scope.role == PlanRole.ADMIN
    assert not scope.own_contractors_only


# ── Daily plan ────────────────────────────────────────────────────────────────


async def _daily_contractors(client, **params) -> set[str]:
    response = await client.get(
        f"{API}/plan-naryad/daily",
        params={"target_date": str(DAY), "housing_id": str(params.pop("housing_id")), **params},
    )
    assert response.status_code == 200, response.text
    return {row["contractor_id"] for row in response.json()["data"]["items"]}


async def test_daily_plan_internal_sees_all_until_a_contractor_is_chosen(role_client, two_contractors):
    client, _ = role_client
    house, first, second = two_contractors.housings[0], *two_contractors.contractors[:2]

    assert await _daily_contractors(client, housing_id=house.id) == {str(first.id), str(second.id)}
    assert await _daily_contractors(client, housing_id=house.id, contractor_id=second.id) == {str(second.id)}


async def test_daily_plan_external_is_forced_to_own_company(role_client, two_contractors):
    client, principal = role_client
    principal["user"] = _external(two_contractors)
    house, first, second = two_contractors.housings[0], *two_contractors.contractors[:2]

    assert await _daily_contractors(client, housing_id=house.id) == {str(first.id)}
    foreign = await client.get(
        f"{API}/plan-naryad/daily",
        params={"target_date": str(DAY), "housing_id": str(house.id), "contractor_id": str(second.id)},
    )
    assert foreign.status_code == 403


async def test_external_without_companies_sees_nothing(role_client, two_contractors):
    client, principal = role_client
    principal["user"] = _external(two_contractors, contractors=[])

    assert await _daily_contractors(client, housing_id=two_contractors.housings[0].id) == set()


# ── Dashboard ─────────────────────────────────────────────────────────────────


async def test_dashboard_counts_follow_the_selector(role_client, two_contractors):
    client, principal = role_client
    params = {"housing_id": str(two_contractors.housings[0].id), "date_from": str(DAY), "date_to": str(DAY)}

    everyone = (await client.get(f"{API}/dashboard/overview", params=params)).json()["data"]
    principal["user"] = _external(two_contractors)
    own = (await client.get(f"{API}/dashboard/overview", params=params)).json()["data"]

    assert (everyone["total_work_facts"], everyone["total_reconciliation_results"], everyone["total_alerts"]) == (
        2,
        2,
        2,
    )
    assert (own["total_work_facts"], own["total_reconciliation_results"], own["total_alerts"]) == (1, 1, 1)
    assert own["total_plan_items"] == everyone["total_plan_items"] - 1


async def test_dashboard_sections_follow_the_selector(role_client, two_contractors):
    client, _ = role_client
    params = {
        "housing_id": str(two_contractors.housings[0].id),
        "date_from": str(DAY),
        "date_to": str(DAY),
        "contractor_id": str(two_contractors.contractors[1].id),
    }

    response = await client.get(f"{API}/dashboard/sections", params=params)

    assert response.status_code == 200, response.text
    [row] = response.json()["data"]
    assert (row["total_plan_items"], row["total_work_facts"], row["total_reconciliation_results"]) == (1, 1, 1)


# ── Reconciliation ────────────────────────────────────────────────────────────


async def test_results_selector_narrows_the_column_filter(role_client, two_contractors):
    client, _ = role_client
    first, second = two_contractors.contractors[:2]
    params = {"housing_id": str(two_contractors.housings[0].id), "contractor_id__in": [str(first.id), str(second.id)]}

    both = (await client.get(f"{API}/reconciliation/results", params=params)).json()["data"]
    narrowed = (
        await client.get(f"{API}/reconciliation/results", params={**params, "contractor_id": str(second.id)})
    ).json()["data"]

    assert {r["contractor_id"] for r in both} == {str(first.id), str(second.id)}
    assert {r["contractor_id"] for r in narrowed} == {str(second.id)}


async def test_results_and_filter_options_are_forced_for_external(role_client, two_contractors):
    client, principal = role_client
    principal["user"] = _external(two_contractors)
    housing, first = str(two_contractors.housings[0].id), str(two_contractors.contractors[0].id)

    results = (await client.get(f"{API}/reconciliation/results", params={"housing_id": housing})).json()["data"]
    options = (await client.get(f"{API}/reconciliation/filter-options", params={"housing_id": housing})).json()

    assert {r["contractor_id"] for r in results} == {first}
    assert [c["id"] for c in options["data"]["contractors"]] == [first]


async def _summaries(client, **params) -> dict:
    response = await client.get(
        f"{API}/reconciliation/summaries",
        params={"date_from": str(SUMMARY_DAY), "date_to": str(LONE_DAY), **params},
    )
    assert response.status_code == 200, response.text
    return {row["date"]: row for row in response.json()["data"]}


async def test_summaries_without_a_selection_are_the_stored_rows(role_client, two_contractors):
    client, _ = role_client

    rows = await _summaries(client, housing_id=str(two_contractors.housings[0].id))

    assert rows[str(SUMMARY_DAY)]["total_planned"] == 3
    assert set(rows) == {str(SUMMARY_DAY), str(LONE_DAY)}


async def test_summaries_are_rebuilt_from_the_selected_contractor(role_client, two_contractors):
    client, _ = role_client
    second = str(two_contractors.contractors[1].id)

    rows = await _summaries(client, housing_id=str(two_contractors.housings[0].id), contractor_id=second)

    day = rows[str(SUMMARY_DAY)]
    assert (day["total_planned"], day["total_done_full"], day["total_unplanned"]) == (1, 1, 1)
    assert (day["completion_rate"], day["weighted_completion"], day["submission_rate"]) == ("1.0000",) * 3
    assert set(day["contractor_details"]) == {second}


async def test_summaries_external_sees_only_own_days_and_stats(role_client, two_contractors):
    client, principal = role_client
    principal["user"] = _external(two_contractors)
    first = str(two_contractors.contractors[0].id)

    rows = await _summaries(client, housing_id=str(two_contractors.housings[0].id))

    assert set(rows) == {str(SUMMARY_DAY)}  # the day only contractor 1 worked on is gone
    day = rows[str(SUMMARY_DAY)]
    assert (day["total_planned"], day["total_done_full"], day["total_no_report"]) == (2, 1, 1)
    assert (day["completion_rate"], day["submission_rate"]) == ("0.5000", "0.5000")
    assert set(day["contractor_details"]) == {first}


# ── Contractor options ────────────────────────────────────────────────────────


async def test_contractor_list_is_own_company_for_external(role_client, two_contractors):
    client, principal = role_client
    principal["user"] = _external(two_contractors)

    rows = (await client.get(f"{API}/contractors/")).json()["data"]

    assert [r["id"] for r in rows] == [str(two_contractors.contractors[0].id)]


async def test_available_contractors_are_own_company_for_external(role_client, two_contractors, monkeypatch):
    client, principal = role_client
    principal["user"] = _external(two_contractors)
    first, second = two_contractors.contractors[:2]
    monkeypatch.setattr(
        ContractorWorksService, "get_contractors_for_cell", AsyncMock(return_value=[first.id, second.id])
    )

    response = await client.get(
        f"{API}/plan-naryad/available-contractors",
        params={"work_id": str(two_contractors.work.id), "floor_id": str(two_contractors.floors[0].id)},
    )

    assert response.status_code == 200, response.text
    assert [r["id"] for r in response.json()["data"]] == [str(first.id)]
