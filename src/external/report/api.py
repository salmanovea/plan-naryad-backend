"""
HTTP client for the Raport reference APIs.

`ReportApi` owns everything related to talking to Raport: it obtains a fresh
Keycloak Bearer token via `get_report_access_token()` on every call (no caching),
issues the request, and paginates list endpoints via `list_all`.

Method names follow the convention `<verb>_<entity>[_<by_parent>]`:
  - list_projects()                     → GET /api/v1/projects
  - list_project_queues(project_id)     → GET /api/v1/projects/{project_id}/queues
  - list_contractor_contracts(...)      → GET /api/v1/contractors/{contractor_id}/contracts/

Consumers pass extra query parameters (pagination, search, ordering, filters)
as keyword arguments. For full-list retrieval use `list_all("<method>", **params)`,
which walks every page and returns the flat list of items.
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


class ReportApi:
    """Thin HTTP client around the Raport reference endpoints."""

    _PER_PAGE = 200

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

        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=app_config.keycloak_verify_ssl,
        ) as http:
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

    async def list_all(self, method_name: str, **kwargs: Any) -> list[dict]:
        """Paginate through a Raport list endpoint and return all items as a flat list.

        Stops when the envelope's `pagination.next_page` is null/absent (or a page
        comes back empty). The Raport pagination envelope uses
        `{total_items, page, items_per_page, next_page, prev_page, total_pages}`.
        """
        method = getattr(self, method_name)
        page, results = 1, []
        while True:
            resp = await method(page=page, per_page=self._PER_PAGE, **kwargs)
            items = resp.get("data", [])
            results.extend(items)
            next_page = (resp.get("pagination") or {}).get("next_page")
            if not next_page or not items:
                break
            page = next_page
        return results

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

    async def list_users(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/users", params=params)

    async def list_contractors(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/contractors", params=params)

    async def list_contracts(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/contracts", params=params)

    async def list_assignments_aggregated(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/contractor-works/assignments-aggregated", params=params)

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

    async def get_housing_work_cells_by_work(self, housing_id: UUID, work_id: UUID, **params: Any) -> Any:
        """Cells of one work across a housing.

        Returns `{"overall": {...}, "data": [<cell>, ...]}` where each cell carries
        `section`, `floor`, `work_cell_id`, `percent_fact` and
        `work_cell_contractors_data[]` (wcc id + contractor). The work itself is the
        path parameter, so this is the only endpoint that ties a cell to a work.

        Note: the OpenAPI schema declares `data` as a single object, but the handler
        returns a list — see `_prepare_response_data_2` in megashablon.
        """
        return await self._request("GET", f"/api/v1/work-cells/{housing_id}/work/{work_id}", params=params)

    async def list_section_work_cells(self, section_id: UUID, **params: Any) -> Any:
        """Cells of a whole section, one row per work.

        Returns `{"overall": {...}, "data": [<work>, ...]}`; each row carries `work_type`,
        `work_group` and `work_cells[]`, and every cell names its `floor`, `is_enabled` and
        `work_cell_contractors_data[]`. This is the only endpoint that says **which works apply
        to which floor**, which is what narrows the manual-add dialog.

        Accepts `template_id`; omit it (never send it empty) to take works from every template.
        Answered 500 on every section until Raport's fix of 17 Aug 2026 — see item 6 in
        docs/raport-change-requests-done.md.
        """
        return await self._request("GET", f"/api/v1/work-cells/section/{section_id}", params=params)

    async def list_work_cell_details(self, work_cell_ids: str, **params: Any) -> Any:
        """Per-cell detail incl. `history[]` (dated facts) and contractor identity.

        `work_cell_ids` is a comma-separated list.
        """
        return await self._request(
            "GET",
            "/api/v1/work-cells/details",
            params={"work_cell_ids": work_cell_ids, **params},
        )

    async def list_work_facts(self, **params: Any) -> Any:
        """Flat list of work facts, filterable by `housing_id` and `work_date__gte/__lte`.

        Since the Raport change of 17 Aug 2026 each row carries `percent` — the payload that
        actually matters, because 99.2% of facts have `volume = 0` — plus `contractor` and
        `work_cell_contractor_id`. Those two come from `work_cell_contractor` and are empty
        on most rows, so the contractor is resolved locally from the cell's assignment.
        """
        return await self._request("GET", "/api/v1/work-facts", params=params)

    async def list_contractor_works(self, **params: Any) -> Any:
        """Detailed contractor assignments down to the floor.

        Filterable by `housing_id`, `section_id`, `floor_id`, `work_id`, `contractor_id`
        and paginated, so both callers (plan generation per housing, the manual-add
        dropdown per work+floor) stay cheap.
        """
        return await self._request("GET", "/api/v1/contractor-works", params=params)


    async def check_calendar_plan(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/calendar-plans/check", params=params)

    async def get_calendar_plan(self, calendar_plan_id: str, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/calendar-plans/{calendar_plan_id}", params=params)

    async def list_plan_templates(self, **params: Any) -> Any:
        return await self._request("GET", "/api/v1/plan-templates", params=params)

    async def get_plan_template_data(self, plan_template_id: str, **params: Any) -> Any:
        return await self._request("GET", f"/api/v1/plan-templates/{plan_template_id}/data", params=params)

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
