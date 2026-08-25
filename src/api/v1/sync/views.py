from typing import Optional

from datetime import date

from fastapi import APIRouter, Depends

from src.api.schemes import DataResponseSchema, ResponseGroup
from src.api.v1.sync.schemes import (
    ImportConstructionObjectsRequest,
    ImportContractorsRequest,
    ImportContractsRequest,
    ImportFloorsRequest,
    ImportHousingsRequest,
    ImportProjectsRequest,
    ImportSectionsRequest,
    ImportUsersRequest,
    ImportWorksRequest,
    ImportWorkTypesRequest,
    SyncImportRequest,
    SyncRequest,
)
from src.services.sync.service import SyncReportService, get_sync_report_service
from src.utils.helpers import catch_all_exceptions, get_responses

sync_router = APIRouter(prefix="/sync", tags=["Sync"])


# ---------------------------------------------------------------------------
# Unified entry points — select entities via the optional `entities` list
# (null/empty = all). `/sync` pulls from Raport; `/sync/import` reads payload.
# ---------------------------------------------------------------------------


@sync_router.post(
    "",
    summary="Sync selected entities from Raport",
    description="Live-sync the chosen reference entities from Raport. Omit `entities` (or leave it empty) to sync all.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_all(
    payload: SyncRequest | None = None,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    entities = payload.entities if payload else None
    result = await service.sync(entities)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/work-facts",
    summary="Sync work facts for a housing from Raport",
    description="Mirrors facts for one housing and date window. Without dates the window is "
    "yesterday and today, which is what the nightly run needs.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_work_facts(
    housing_raport_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_work_facts(housing_raport_id, date_from=date_from, date_to=date_to)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import",
    summary="Import selected entities from payload",
    description="Offline-import the chosen reference entities from the request body. "
    "Omit `entities` to process every entity that has a payload list.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_all(
    payload: SyncImportRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_entities(payload)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/objects",
    summary="Sync objects hierarchy from Raport",
    description="Pulls Project → ConstructionObject → Housing → Section → Floor from Raport and upserts locally.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_objects(
    project_raport_id: Optional[str] = None,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_objects(project_raport_id=project_raport_id)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/work-catalog",
    summary="Sync work catalog from Raport",
    description="Pulls WorkGroup → WorkType from Raport and upserts locally.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_work_catalog(
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_work_catalog()
    return DataResponseSchema(data=result)


@sync_router.post(
    "/users",
    summary="Sync users from Raport",
    description="Pulls the user directory from Raport and upserts locally.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_users(
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_users()
    return DataResponseSchema(data=result)


@sync_router.post(
    "/contractors",
    summary="Sync contractors from Raport",
    description="Pulls the contractor list from Raport and upserts locally.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_contractors(
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_contractors()
    return DataResponseSchema(data=result)


@sync_router.post(
    "/contracts",
    summary="Sync contracts from Raport",
    description="Pulls the flat contract list from Raport and upserts locally (contractor resolved by raport_id).",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_contracts(
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_contracts()
    return DataResponseSchema(data=result)


@sync_router.post(
    "/tech-sequence",
    summary="Sync the technological sequence for a housing from Raport",
    description="Builds the tech sequence for one housing from its calendar plan (or the default "
    "plan-template if none): plan links → depends_on, keyed by (housing, work_type). "
    "Reconciles source='raport' rows (volumes are preserved on re-sync).",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_tech_sequence(
    housing_raport_id: str,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_tech_sequence(housing_raport_id=housing_raport_id)
    return DataResponseSchema(data=result)


# ---------------------------------------------------------------------------
# Payload-driven imports — push reference data from an offline xlsx dump.
#
# Same upsert semantics as /sync/* but data comes from the request body.
# Parents are referenced by their Raport id (`*_raport_id`); items whose
# parent isn't yet in the local DB are counted in `missing_parents` and
# skipped.
# ---------------------------------------------------------------------------


@sync_router.post(
    "/import/projects",
    summary="Import workforce projects from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_projects(
    payload: ImportProjectsRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_projects(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/construction-objects",
    summary="Import construction objects from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_construction_objects(
    payload: ImportConstructionObjectsRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_construction_objects(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/housings",
    summary="Import housings from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_housings(
    payload: ImportHousingsRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_housings(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/sections",
    summary="Import sections from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_sections(
    payload: ImportSectionsRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_sections(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/floors",
    summary="Import floors from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_floors(
    payload: ImportFloorsRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_floors(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/work-types",
    summary="Import work types («Виды работ») from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_work_types(
    payload: ImportWorkTypesRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_work_types(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/works",
    summary="Import works («Работы») from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_works(
    payload: ImportWorksRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_works(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/users",
    summary="Import users from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_users(
    payload: ImportUsersRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_users(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/contractors",
    summary="Import contractors from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_contractors(
    payload: ImportContractorsRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_contractors(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/contracts",
    summary="Import contracts from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_contracts(
    payload: ImportContractsRequest,
    service: SyncReportService = Depends(get_sync_report_service),
) -> DataResponseSchema[dict]:
    result = await service.import_contracts(payload.items)
    return DataResponseSchema(data=result)
