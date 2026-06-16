import pytest

from tests.constants import API


@pytest.mark.smoke
async def test_workforce_dashboard_returns_200(client):
    response = await client.get(f"{API}/workforce/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    data = body["data"]
    assert "projects" in data
    assert isinstance(data["projects"], list)


@pytest.mark.smoke
async def test_list_wf_projects_returns_200(client):
    response = await client.get(f"{API}/workforce/projects")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)


@pytest.mark.smoke
async def test_list_violations_returns_200(client):
    response = await client.get(f"{API}/workforce/violations")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)


@pytest.mark.smoke
async def test_list_norms_returns_200(client):
    response = await client.get(f"{API}/workforce/norms")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["data"], list)


async def test_get_wf_project_not_found_returns_404(client):
    response = await client.get(f"{API}/workforce/projects/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "404"


async def test_create_wf_project_returns_201(client):
    response = await client.post(
        f"{API}/workforce/projects",
        json={"name": "Тестовый проект", "project_class": "Комфорт"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["data"]["name"] == "Тестовый проект"
    assert "id" in body["data"]


async def test_scan_violations_returns_200(client):
    response = await client.post(f"{API}/workforce/violations/scan")

    assert response.status_code == 200
    body = response.json()
    assert "created" in body["data"]


async def test_system_problems_returns_200(client):
    response = await client.get(f"{API}/workforce/system-problems")

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert "problems" in data
    assert isinstance(data["problems"], list)
