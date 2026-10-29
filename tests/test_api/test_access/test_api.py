"""Registered API + real PostgreSQL; synthetic profiles, no real users or external calls.

Root conftest recreates DB_TEST_DATABASE_NAME: use a NEW disposable database for this suite.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.middlewares.raport_auth.backend import ServiceUser
from src.models.dbo import models as m
from src.services.contractor_works.service import ContractorWorksService
from src.services.report_cells import HousingSlice, ReportCellsService
from tests.constants import API
from tests.fixtures.access import DAY, profile


async def test_contractor_list_counts_pagination_and_status(role_client, access_data):
    client, principal = role_client
    principal["user"] = profile(access_data, ["contractor", "factgathering_user", "factgathering_editor"])
    response = await client.get(f"{API}/plan-naryad/", params={"per_page": 1})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["pagination"]["total_items"] == 1
    assert [row["id"] for row in payload["data"]] == [str(access_data.plans[0][2].id)]
    assert payload["data"][0]["status"] == "transferred"
    second = await client.get(f"{API}/plan-naryad/", params={"per_page": 1, "page": 2})
    assert second.json()["data"] == []
    draft = await client.get(f"{API}/plan-naryad/", params={"status": "draft"})
    assert draft.json()["data"] == []


async def test_daily_contractor_views_and_selectors(role_client, access_data):
    client, principal = role_client
    principal["user"] = profile(access_data, ["contractor", "factgathering_user"])
    for path, extra in (
        ("/plan-naryad/daily", {"housing_id": str(access_data.housings[0].id)}),
        ("/plan-naryad/contractor", {"contractor_id": str(access_data.contractors[0].id)}),
    ):
        response = await client.get(API + path, params={"target_date": str(DAY), **extra})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["total_items"] == 1
    for path, expected in [
        ("/workforce/projects", access_data.projects[0].id),
        ("/housings/", access_data.housings[0].id),
    ]:
        rows = (await client.get(API + path)).json()["data"]
        assert [row["id"] for row in rows] == [str(expected)]


@pytest.mark.parametrize("selector", ["housing", "contractor", "plan", "draft", "project", "raport_housing"])
async def test_contractor_foreign_and_nontransferred_data_denied(role_client, access_data, selector):
    client, principal = role_client
    principal["user"] = profile(access_data, ["contractor"])
    requests = {
        "housing": ("/plan-naryad/daily", {"housing_id": str(access_data.housings[1].id), "target_date": str(DAY)}),
        "contractor": (
            "/plan-naryad/contractor",
            {"contractor_id": str(access_data.contractors[1].id), "target_date": str(DAY)},
        ),
        "plan": (f"/plan-naryad/{access_data.plans[1][2].id}", {}),
        "draft": (f"/plan-naryad/{access_data.plans[0][0].id}", {}),
        "project": ("/housings/", {"project_id": str(access_data.projects[1].id)}),
        "raport_housing": (
            "/plan-naryad/daily-assignment",
            {
                "housing_raport_id": access_data.housings[1].raport_id,
                "date": str(DAY),
            },
        ),
    }
    path, params = requests[selector]
    assert (await client.get(API + path, params=params)).status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/overview",
        "/reconciliation/results",
        "/alerts/",
        "/workforce/dashboard",
        "/workforce/headcount/facts",
        "/works/",
        "/work-facts/",
        "/plan-naryad/available-works",
        "/plan-naryad/available-contractors",
    ],
)
async def test_contractor_other_sections_denied_before_parameter_validation(role_client, access_data, path):
    client, principal = role_client
    principal["user"] = profile(access_data, ["contractor", "factgathering_user"])
    assert (await client.get(API + path)).status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/plan-naryad/generate"),
        ("POST", "/plan-naryad/"),
        ("POST", "/plan-naryad/bulk-confirm"),
        ("POST", "/plan-naryad/bulk-delete"),
        ("POST", "/plan-naryad/transfer"),
        ("DELETE", "/plan-naryad/{id}"),
        ("POST", "/plan-naryad/{id}/confirm"),
        ("PUT", "/housings/{housing}"),
    ],
)
async def test_contractor_mutations_denied(role_client, access_data, method, path):
    client, principal = role_client
    principal["user"] = profile(access_data, ["contractor", "factgathering_user"])
    path = path.format(id=access_data.plans[0][2].id, housing=access_data.housings[0].id)
    assert (await client.request(method, API + path, json={})).status_code == 403


@pytest.mark.parametrize("assignment", ["empty", "unmapped", "local_id"])
async def test_missing_project_assignments_never_expand_access(role_client, access_data, assignment):
    client, principal = role_client
    projects = {"empty": [], "unmapped": [str(uuid4())], "local_id": [str(access_data.projects[0].id)]}[assignment]
    principal["user"] = profile(access_data, projects=projects)
    for path in ["/plan-naryad/", "/housings/", "/workforce/projects", "/reconciliation/results", "/alerts/"]:
        response = await client.get(API + path)
        assert response.status_code == 200, response.text
        assert response.json()["data"] == []


@pytest.mark.parametrize("contractors", [[], ["unmapped"]])
async def test_missing_contractor_assignments_never_expand_access(role_client, access_data, contractors):
    client, principal = role_client
    principal["user"] = profile(access_data, ["contractor"], contractors=contractors)
    assert (await client.get(f"{API}/plan-naryad/")).json()["data"] == []


async def test_rs_dashboard_totals_and_plan_list_scoped(role_client, access_data):
    client, _ = role_client
    rows = (await client.get(f"{API}/plan-naryad/")).json()
    assert rows["pagination"]["total_items"] == 5
    assert {r["housing_id"] for r in rows["data"]} == {str(access_data.housings[0].id)}
    response = await client.get(f"{API}/dashboard/overview", params={"date_from": str(DAY), "date_to": str(DAY)})
    assert response.status_code == 200, response.text
    totals = response.json()["data"]
    for key, expected in [
        ("total_plan_items", 5),
        ("total_work_facts", 1),
        ("total_reconciliation_results", 1),
        ("total_alerts", 1),
    ]:
        assert totals[key] == expected


@pytest.mark.parametrize(
    "path",
    [
        "/reconciliation/results",
        "/reconciliation/summaries",
        "/alerts/",
        "/work-facts/",
        "/workforce/headcount/facts",
    ],
)
async def test_rs_other_section_lists_scoped(role_client, access_data, path):
    client, _ = role_client
    response = await client.get(API + path)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 1
    for row in rows:
        if "housing_id" in row:
            assert row["housing_id"] == str(access_data.housings[0].id)
        if "project_id" in row:
            assert row["project_id"] == str(access_data.projects[0].id)


@pytest.mark.parametrize("path", ["/workforce/dashboard", "/workforce/contractor-rating", "/workforce/system-problems"])
async def test_rs_aggregate_queries_execute_scoped(role_client, access_data, path):
    client, _ = role_client
    response = await client.get(API + path)
    assert response.status_code == 200, response.text
    assert str(access_data.projects[1].id) not in response.text
    if path == "/workforce/dashboard":
        assert response.json()["data"]["total_net_bdr"] == "1000.00"


@pytest.mark.parametrize("section", ["detail", "forecast"])
async def test_rs_workforce_project_details_with_budget_data(role_client, access_data, section):
    client, _ = role_client
    response = await client.get(f"{API}/workforce/projects/{access_data.projects[0].id}/{section}")
    assert response.status_code == 200, response.text
    assert str(access_data.projects[1].id) not in response.text


@pytest.mark.parametrize("operation", ["bulk-confirm", "bulk-delete"])
async def test_rs_mixed_batches_rejected_before_writes_and_logs(role_client, access_data, operation):
    client, _ = role_client
    response = await client.post(
        f"{API}/plan-naryad/{operation}",
        json={
            "ids": [str(access_data.plans[0][0].id), str(access_data.plans[1][0].id)],
        },
    )
    assert response.status_code == 403, response.text
    assert (await access_data.db.execute(select(func.count()).select_from(m.ActionLog))).scalar() == 0
    assert (await access_data.db.get(m.PlanItem, access_data.plans[0][0].id)).status == "draft"


async def test_rs_foreign_generation_rejected_before_journalling(role_client, access_data):
    client, _ = role_client
    response = await client.post(
        f"{API}/plan-naryad/generate",
        json={
            "housing_id": str(access_data.housings[1].id),
            "date": str(DAY),
            "force": True,
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "403"
    assert (await access_data.db.execute(select(func.count()).select_from(m.ActionLog))).scalar() == 0


async def test_rs_can_confirm_and_delete_own_position(role_client, access_data):
    client, _ = role_client
    own = access_data.plans[0][0].id
    response = await client.post(f"{API}/plan-naryad/{own}/confirm", json={})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "draft"
    assert response.json()["data"]["rs_confirmed"] is True
    assert (await client.delete(f"{API}/plan-naryad/{own}")).status_code == 200


async def test_admin_plus_contractor_has_unrestricted_access(role_client, access_data):
    client, principal = role_client
    principal["user"] = profile(access_data, ["superuser", "contractor"], projects=[], contractors=[])
    response = await client.get(f"{API}/plan-naryad/")
    assert response.status_code == 200
    assert response.json()["pagination"]["total_items"] == 10
    assert (await client.get(f"{API}/housings/{access_data.housings[1].id}")).status_code == 200


@pytest.mark.parametrize("groups", [["supervisor"], ["plan_naryad"], ["factgathering_editor"], ["unknown"], []])
async def test_unsupported_roles_denied_at_registered_api(role_client, access_data, groups):
    client, principal = role_client
    principal["user"] = profile(access_data, groups)
    response = await client.get(f"{API}/plan-naryad/")
    assert response.status_code == 403
    assert response.json() == {"code": "403", "message": "Нет доступа к план-наряду."}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/housings/"),
        ("GET", "/works/groups"),
        ("GET", "/contractors/"),
        ("GET", "/work-facts/"),
        ("GET", "/plan-naryad/"),
        ("GET", "/reconciliation/results"),
        ("GET", "/alerts/"),
        ("GET", "/dashboard/overview"),
        ("GET", "/workforce/projects"),
        ("POST", "/sync/import"),
        ("POST", "/tasks/transfer"),
        ("GET", "/users/me"),
    ],
)
async def test_unsupported_role_denied_in_every_api_section(role_client, access_data, method, path):
    client, principal = role_client
    principal["user"] = profile(access_data, ["unknown"])

    response = await client.request(method, API + path)

    assert response.status_code == 403
    assert response.json() == {"code": "403", "message": "Нет доступа к план-наряду."}


@pytest.mark.parametrize("path", ["/users/me", "/plan-naryad/", "/workforce/projects"])
async def test_machine_has_no_universal_api_bypass(role_client, path):
    client, principal = role_client
    principal["user"] = ServiceUser("api")
    assert (await client.get(API + path)).status_code == 403


async def test_machine_sync_is_not_an_allowed_integration(role_client):
    client, principal = role_client
    principal["user"] = ServiceUser("api")
    assert (await client.post(API + "/sync")).status_code == 403


async def test_machine_daily_assignment_integration_preserved(role_client, access_data):
    client, principal = role_client
    principal["user"] = ServiceUser("api")
    response = await client.get(
        f"{API}/plan-naryad/daily-assignment",
        params={
            "housing_raport_id": access_data.housings[1].raport_id,
            "date": str(DAY),
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]) == 2


async def test_rs_manual_add_uses_live_assignment_for_previously_unseen_contractor(
    role_client, access_data, monkeypatch
):
    client, _ = role_client
    contractor = access_data.contractors[2]
    rows = [
        {
            "contractor": {"id": contractor.raport_id},
            "section": {"id": access_data.sections[0].raport_id},
            "floor": {"id": access_data.floors[0].raport_id},
            "work": {"id": access_data.work.raport_id},
        }
    ]
    monkeypatch.setattr(ContractorWorksService, "_fetch_all", AsyncMock(return_value=rows))
    monkeypatch.setattr(ReportCellsService, "get_housing_slice", AsyncMock(return_value=HousingSlice()))
    response = await client.post(
        f"{API}/plan-naryad/",
        json={
            "date": str(DAY),
            "housing_id": str(access_data.housings[0].id),
            "section_id": str(access_data.sections[0].id),
            "floor_id": str(access_data.floors[0].id),
            "work_id": str(access_data.work.id),
            "contractor_id": str(contractor.id),
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["contractor_id"] == str(contractor.id)
    assert response.json()["data"]["status"] == "draft"


@pytest.mark.parametrize("operation", ["bulk-confirm", "bulk-delete"])
async def test_rs_valid_batches_are_allowed(role_client, access_data, operation):
    client, _ = role_client
    response = await client.post(
        f"{API}/plan-naryad/{operation}",
        json={
            "ids": [str(access_data.plans[0][0].id), str(access_data.plans[0][1].id)],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["confirmed" if operation == "bulk-confirm" else "deleted"] == 2


async def test_generation_mixed_hierarchy_rejected_before_journalling(role_client, access_data):
    client, principal = role_client
    principal["user"] = profile(access_data, projects=[p.raport_id for p in access_data.projects])
    response = await client.post(
        f"{API}/plan-naryad/generate",
        json={
            "housing_id": str(access_data.housings[0].id),
            "section_id": str(access_data.sections[1].id),
            "date": str(DAY),
            "force": True,
        },
    )
    assert response.status_code == 400
    assert (await access_data.db.execute(select(func.count()).select_from(m.ActionLog))).scalar() == 0


@pytest.mark.parametrize("path", ["/users/me", "/works/", "/workforce/projects"])
async def test_undeclared_foreign_query_parameter_is_ignored(role_client, access_data, path):
    client, _ = role_client
    response = await client.get(API + path, params={"project_id": str(access_data.projects[1].id)})
    assert response.status_code == 200, response.text


async def test_missing_token_denied_by_real_middleware(role_client):
    client, _ = role_client
    client.headers.clear()
    response = await client.get(API + "/plan-naryad/")
    assert response.status_code == 401
    assert response.json()["code"] == "401"
    assert response.json()["message"]


@pytest.mark.parametrize(
    "path",
    [
        "/housings/{housing}",
        "/housings/{housing}/structure",
        "/housings/{housing}/sections",
        "/housings/sections/{section}/floors",
        "/works/tech-sequence/{housing}",
        "/workforce/projects/{project}",
        "/workforce/projects/{project}/detail",
        "/workforce/projects/{project}/forecast",
        "/workforce/projects/{project}/objects",
        "/workforce/objects/{obj}/contractors",
    ],
)
async def test_rs_declared_foreign_path_selectors_denied(role_client, access_data, path):
    client, _ = role_client
    path = path.format(
        housing=access_data.housings[1].id,
        section=access_data.sections[1].id,
        project=access_data.projects[1].id,
        obj=access_data.objects[1].id,
    )
    response = await client.get(API + path)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "403"
    assert response.json()["message"]


@pytest.mark.parametrize(
    "path",
    [
        "/housings/",
        "/work-facts/",
        "/reconciliation/results",
        "/reconciliation/summaries",
        "/alerts/",
        "/workforce/headcount/facts",
        "/workforce/headcount/plans",
        "/workforce/challenges",
    ],
)
async def test_rs_declared_foreign_query_selectors_denied(role_client, access_data, path):
    client, _ = role_client
    params = (
        {"project_id": str(access_data.projects[1].id)}
        if path.startswith("/workforce")
        else {"housing_id": str(access_data.housings[1].id)}
    )
    if path == "/housings/":
        params = {"construction_object_id": str(access_data.objects[1].id)}
    response = await client.get(API + path, params=params)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "403"


async def test_rs_challenge_creation_and_listing_with_items(role_client, access_data):
    client, _ = role_client
    payload = {
        "project_id": str(access_data.projects[0].id),
        "construction_object_id": str(access_data.objects[0].id),
        "period_month": str(DAY.replace(day=1)),
        "items": [{"work_id": str(access_data.work.id), "requested_count": 12}],
    }
    response = await client.post(API + "/workforce/challenges", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["items"][0]["requested_count"] == 12
    listed = await client.get(API + "/workforce/challenges")
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"][0]["id"] == response.json()["data"]["id"]


async def test_rs_headcount_mixed_parent_pair_denied_before_write(role_client, access_data):
    client, principal = role_client
    principal["user"] = profile(access_data, projects=[p.raport_id for p in access_data.projects])
    response = await client.post(
        API + "/workforce/headcount/facts",
        json={
            "project_id": str(access_data.projects[0].id),
            "construction_object_id": str(access_data.objects[1].id),
            "work_id": str(access_data.work.id),
            "fact_date": str(DAY),
            "count": 17,
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "400"


async def test_housing_and_floor_filter_does_not_require_section(role_client, access_data):
    client, _ = role_client
    response = await client.get(
        API + "/plan-naryad/",
        params={
            "housing_id": str(access_data.housings[0].id),
            "floor_id": str(access_data.floors[0].id),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["pagination"]["total_items"] == 5


async def test_declared_foreign_id_collection_is_denied(role_client, access_data):
    client, _ = role_client
    response = await client.get(API + "/plan-naryad/", params={"housing_id__in": [str(access_data.housings[1].id)]})
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "403"


@pytest.mark.parametrize(
    "path",
    [
        "/works/sets",
        "/works/groups",
        "/works/types",
        "/works/",
        "/contractors/",
        "/housings/",
        "/workforce/projects",
        "/workforce/norms",
        "/workforce/article-bdrs",
        "/workforce/article-bdrs/bulk",
        "/workforce/article-mappings",
    ],
)
async def test_rs_common_dictionary_creation_requires_admin(role_client, access_data, path):
    client, _ = role_client
    payloads = {
        "/works/sets": {"name": "Forbidden set", "code": str(uuid4())},
        "/works/groups": {"name": "Forbidden group", "code": str(uuid4())},
        "/works/types": {"name": "Forbidden type", "code": str(uuid4())},
        "/works/": {
            "name": "Forbidden work",
            "code": str(uuid4()),
            "unit": "m2",
            "work_type_id": str(access_data.work.work_type_id),
        },
        "/contractors/": {"name": "Forbidden contractor", "short_name": "Forbidden"},
        "/housings/": {"name": "Forbidden housing", "complex_name": "Forbidden"},
        "/workforce/projects": {"name": "Forbidden project"},
        "/workforce/norms": {
            "work_id": str(access_data.work.id),
            "project_class": "Комфорт",
            "median_day_bdr": "1",
            "median_month_bdr": "22",
        },
        "/workforce/article-bdrs": {"name": "Forbidden article", "code_1c": str(uuid4())},
        "/workforce/article-bdrs/bulk": {"items": [{"name": "Forbidden article", "code_1c": str(uuid4())}]},
        "/workforce/article-mappings": {"article_bdr_id": str(uuid4()), "work_id": str(access_data.work.id)},
    }
    response = await client.post(API + path, json=payloads[path])
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "403"
    assert response.json()["message"]
