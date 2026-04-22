"""
HTTP client for the Raport reference APIs.

Copied into src/external/report/client.py by the report-microservice skill.
Every method is a thin wrapper over `_request`, which obtains a fresh Keycloak
Bearer token via `get_report_access_token()` on every call (no caching).

Method names follow the convention `<verb>_<entity>[_<by_parent>]`:
  - list_projects()                     → GET /api/v1/projects
  - list_project_queues(project_id)     → GET /api/v1/projects/{project_id}/queues
  - list_contractor_contracts(...)      → GET /api/v1/contractors/{contractor_id}/contracts/

Consumers pass extra query parameters (pagination, search, ordering, filters)
as keyword arguments.
"""

from typing import Any
from uuid import UUID

import httpx

from src.config.logger import LoggerProvider
from src.config.settings import app_config
from src.external.report.auth import get_report_access_token

log = LoggerProvider().get_logger(__name__)


class ReportApiError(RuntimeError):
    """Raised when the Raport API responds with a non-2xx status."""

    def __init__(self, status_code: int, message: str):
        super().__init__(f"Raport API {status_code}: {message}")
        self.status_code = status_code


class ReportClient:
    """Thin HTTP client around the Raport reference endpoints."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        base = (base_url or app_config.report_api_url or "").rstrip("/")
        if not base:
            raise RuntimeError("REPORT_API_URL is not set")
        self.base_url = base
        self.timeout = timeout

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a single HTTP request with a fresh Bearer token."""
        token = await get_report_access_token()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{self.base_url}{path}"

        async with httpx.AsyncClient(timeout=self.timeout) as http:
            response = await http.request(
                method,
                url,
                params=clean_params,
                headers={"Authorization": f"Bearer {token}"},
            )

        if response.status_code >= 400:
            log.error(f"Raport API {method} {path} failed: status={response.status_code} body={response.text[:500]}")
            raise ReportApiError(response.status_code, response.text[:500])

        return response.json()

    # ------------------------------------------------------------------
    # Chain 1 — Project → Queue → Construction Object → Housing → Section → Floor
    # ------------------------------------------------------------------

    async def list_projects(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/projects", params=params)

    async def get_project_structure(self, project_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/projects/{project_id}/structure", params=params)

    async def list_project_queues(self, project_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/projects/{project_id}/queues", params=params)

    async def list_queue_construction_objects(self, queue_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/queues/{queue_id}/construction-objects", params=params)

    async def list_queue_housings(self, queue_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/queues/{queue_id}/housings", params=params)

    async def list_construction_object_housings(self, construction_object_id: UUID, **params: Any) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/construction-objects/{construction_object_id}/housings",
            params=params,
        )

    async def get_housing_structure(self, housing_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/housings/{housing_id}/structure", params=params)

    async def get_housing_structure_with_contractors(self, housing_id: UUID, **params: Any) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/housings/{housing_id}/structure-with-contractors",
            params=params,
        )

    async def list_housing_sections(self, housing_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/housings/{housing_id}/sections", params=params)

    async def list_section_floors(self, section_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/sections/{section_id}/floors", params=params)

    # ------------------------------------------------------------------
    # Chain 2 — Contractor → Contract
    # ------------------------------------------------------------------

    async def list_contractors(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/contractors", params=params)

    async def list_project_contractors(self, project_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/contractors/project/{project_id}", params=params)

    async def list_queue_contractors(self, queue_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/queues/{queue_id}/contractors", params=params)

    async def list_construction_object_contractors(self, construction_object_id: UUID, **params: Any) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/construction-objects/{construction_object_id}/contractors",
            params=params,
        )

    async def list_housing_contractors(self, housing_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/housings/{housing_id}/contractors", params=params)

    async def list_section_contractors(self, section_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/sections/{section_id}/contractors", params=params)

    async def list_floor_contractors(self, floor_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/floors/{floor_id}/contractors", params=params)

    async def list_contractor_contracts(self, contractor_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/contractors/{contractor_id}/contracts/", params=params)

    async def list_project_contractor_contracts(
        self,
        project_id: UUID,
        contractor_id: UUID,
        **params: Any,
    ) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/contracts/project/{project_id}/contractor/{contractor_id}",
            params=params,
        )

    # ------------------------------------------------------------------
    # Chain 3 — Work Set → Work Group → Work Type → Work
    # ------------------------------------------------------------------

    async def list_construction_object_work_sets(self, construction_object_id: UUID, **params: Any) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/construction-objects/{construction_object_id}/work-sets",
            params=params,
        )

    async def list_work_set_work_groups(self, work_set_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/work-sets/{work_set_id}/work-groups", params=params)

    async def list_work_groups(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/work-groups", params=params)

    async def list_housing_work_groups(self, housing_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/housings/{housing_id}/work-groups", params=params)

    async def list_contractor_work_groups(self, contractor_id: UUID, **params: Any) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/contractors/{contractor_id}/work-groups/",
            params=params,
        )

    async def list_work_group_work_types(self, work_group_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/work-groups/{work_group_id}/work-types", params=params)

    async def list_work_type_works(self, work_type_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/work-types/{work_type_id}/works", params=params)

    async def get_works_structure(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/works/structure", params=params)

    # ------------------------------------------------------------------
    # Chain 4 — Position
    # ------------------------------------------------------------------

    async def list_positions(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/positions/", params=params)

    async def list_work_set_positions(self, work_set_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/work-sets/{work_set_id}/positions", params=params)

    async def list_work_group_positions(self, work_group_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/work-groups/{work_group_id}/positions", params=params)

    async def list_work_type_positions(self, work_type_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/work-types/{work_type_id}/positions", params=params)

    async def list_work_positions(self, work_id: UUID, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/works/{work_id}/positions", params=params)
