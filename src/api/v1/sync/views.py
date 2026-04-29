from typing import Optional

from fastapi import APIRouter, Depends

from src.api.schemes import DataResponseSchema, ResponseGroup
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
