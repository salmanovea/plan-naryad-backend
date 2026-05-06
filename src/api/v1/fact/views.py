from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.fact.schemes import (
    CreateWorkFactRequest,
    UpdateWorkFactRequest,
    WorkFactFilters,
    WorkFactSchema,
)
from src.services.fact.service import FactService, get_fact_service
from src.utils.helpers import catch_all_exceptions, get_responses, pagination_params

fact_router = APIRouter(prefix="/work-facts", tags=["Work Facts"])


@fact_router.get("/", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_work_facts(
    filters: WorkFactFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: FactService = Depends(get_fact_service),
) -> ListDataResponseSchema[WorkFactSchema]:
    filter_data = filters.model_dump(exclude_none=True)
    date_from = filter_data.pop("date_from", None)
    date_to = filter_data.pop("date_to", None)
    if date_from:
        filter_data["date__gte"] = date_from
    if date_to:
        filter_data["date__lte"] = date_to

    items = await service.work_fact_manager.search(order_by=["-date"], pagination=pagination, **filter_data)
    total = await service.work_fact_manager.count(**filter_data)
    return ListDataResponseSchema[WorkFactSchema].create(
        list_data=[WorkFactSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@fact_router.get("/{fact_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_work_fact(
    fact_id: UUID,
    service: FactService = Depends(get_fact_service),
) -> DataResponseSchema[WorkFactSchema]:
    item = await service.work_fact_manager.get_by_id(fact_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work fact not found")
    return DataResponseSchema[WorkFactSchema](data=WorkFactSchema.model_validate(item))


@fact_router.post("/", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_work_fact(
    body: CreateWorkFactRequest,
    service: FactService = Depends(get_fact_service),
) -> DataResponseSchema[WorkFactSchema]:
    item = await service.work_fact_manager.create(body.model_dump())
    return DataResponseSchema[WorkFactSchema](data=WorkFactSchema.model_validate(item))


@fact_router.put("/{fact_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_work_fact(
    fact_id: UUID,
    body: UpdateWorkFactRequest,
    service: FactService = Depends(get_fact_service),
) -> DataResponseSchema[WorkFactSchema]:
    item = await service.work_fact_manager.update_by_id(fact_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work fact not found")
    return DataResponseSchema[WorkFactSchema](data=WorkFactSchema.model_validate(item))


@fact_router.delete("/{fact_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_work_fact(
    fact_id: UUID,
    service: FactService = Depends(get_fact_service),
) -> DataResponseSchema[dict]:
    await service.work_fact_manager.delete_by_id(fact_id)
    return DataResponseSchema[dict](data={"deleted": str(fact_id)})
