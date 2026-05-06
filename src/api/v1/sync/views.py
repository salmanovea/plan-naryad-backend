from typing import Optional

from fastapi import APIRouter, Depends

from src.api.schemes import DataResponseSchema, ResponseGroup
from src.api.v1.sync.schemes import (
    ImportConstructionObjectsRequest,
    ImportContractorsRequest,
    ImportFloorsRequest,
    ImportHousingsRequest,
    ImportProjectsRequest,
    ImportSectionsRequest,
    ImportWorkGroupsRequest,
    ImportWorkTypesRequest,
)
from src.services.sync.service import SyncService, get_sync_service
from src.utils.helpers import catch_all_exceptions, get_responses

sync_router = APIRouter(prefix="/sync", tags=["Sync"])


@sync_router.post(
    "/objects",
    summary="Sync objects hierarchy from Raport",
    description="Pulls Project → ConstructionObject → Housing → Section → Floor from Raport and upserts locally.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_objects(
    project_raport_id: Optional[str] = None,
    service: SyncService = Depends(get_sync_service),
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
    service: SyncService = Depends(get_sync_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_work_catalog()
    return DataResponseSchema(data=result)


@sync_router.post(
    "/contractors",
    summary="Sync contractors from Raport",
    description="Pulls the contractor list from Raport and upserts locally.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def sync_contractors(
    service: SyncService = Depends(get_sync_service),
) -> DataResponseSchema[dict]:
    result = await service.sync_contractors()
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
    service: SyncService = Depends(get_sync_service),
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
    service: SyncService = Depends(get_sync_service),
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
    service: SyncService = Depends(get_sync_service),
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
    service: SyncService = Depends(get_sync_service),
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
    service: SyncService = Depends(get_sync_service),
) -> DataResponseSchema[dict]:
    result = await service.import_floors(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/work-groups",
    summary="Import work groups from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_work_groups(
    payload: ImportWorkGroupsRequest,
    service: SyncService = Depends(get_sync_service),
) -> DataResponseSchema[dict]:
    result = await service.import_work_groups(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/work-types",
    summary="Import work types from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_work_types(
    payload: ImportWorkTypesRequest,
    service: SyncService = Depends(get_sync_service),
) -> DataResponseSchema[dict]:
    result = await service.import_work_types(payload.items)
    return DataResponseSchema(data=result)


@sync_router.post(
    "/import/contractors",
    summary="Import contractors from payload",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def import_contractors(
    payload: ImportContractorsRequest,
    service: SyncService = Depends(get_sync_service),
) -> DataResponseSchema[dict]:
    result = await service.import_contractors(payload.items)
    return DataResponseSchema(data=result)
