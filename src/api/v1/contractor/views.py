from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.access import plan_access
from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.contractor.schemes import (
    ContractorFilters,
    ContractorSchema,
    CreateContractorRequest,
    UpdateContractorRequest,
)
from src.services.contractor.service import ContractorService, get_contractor_service
from src.utils.helpers import catch_all_exceptions, get_responses, pagination_params

contractor_router = APIRouter(prefix="/contractors", tags=["Contractors"], dependencies=[Depends(plan_access)])


@contractor_router.get("/", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_contractors(
    filters: ContractorFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: ContractorService = Depends(get_contractor_service),
) -> ListDataResponseSchema[ContractorSchema]:
    filter_data = filters.model_dump(exclude_none=True)
    search_text = filter_data.pop("search", None)
    items = await service.search_contractor(search=search_text, order_by=["name"], pagination=pagination, **filter_data)
    total = await service.count_contractor(search=search_text, **filter_data)
    return ListDataResponseSchema[ContractorSchema].create(
        list_data=[ContractorSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@contractor_router.get("/{contractor_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_contractor(
    contractor_id: UUID,
    service: ContractorService = Depends(get_contractor_service),
) -> DataResponseSchema[ContractorSchema]:
    item = await service.get_contractor(contractor_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor not found")
    return DataResponseSchema[ContractorSchema](data=ContractorSchema.model_validate(item))


@contractor_router.post("/", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_contractor(
    body: CreateContractorRequest,
    service: ContractorService = Depends(get_contractor_service),
) -> DataResponseSchema[ContractorSchema]:
    item = await service.create_contractor(body.model_dump())
    return DataResponseSchema[ContractorSchema](data=ContractorSchema.model_validate(item))


@contractor_router.put("/{contractor_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_contractor(
    contractor_id: UUID,
    body: UpdateContractorRequest,
    service: ContractorService = Depends(get_contractor_service),
) -> DataResponseSchema[ContractorSchema]:
    item = await service.update_contractor(contractor_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor not found")
    return DataResponseSchema[ContractorSchema](data=ContractorSchema.model_validate(item))


@contractor_router.delete("/{contractor_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_contractor(
    contractor_id: UUID,
    service: ContractorService = Depends(get_contractor_service),
) -> DataResponseSchema[dict]:
    await service.delete_contractor(contractor_id)
    return DataResponseSchema[dict](data={"deleted": str(contractor_id)})
