from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.work.schemes import (
    CreateTechSequenceItemRequest,
    CreateWorkGroupRequest,
    CreateWorkTypeRequest,
    TechSequenceItemSchema,
    TechSequenceSchema,
    UpdateWorkGroupRequest,
    UpdateWorkTypeRequest,
    WorkFilters,
    WorkGroupSchema,
    WorkTypeSchema,
)
from src.services.work.service import WorkService, get_work_service
from src.utils.helpers import catch_all_exceptions, get_responses, pagination_params

work_router = APIRouter(prefix="/works", tags=["Works"])


# ── WorkGroup ─────────────────────────────────────────────────────────────────


@work_router.get("/groups", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_work_groups(
    service: WorkService = Depends(get_work_service),
) -> ListDataResponseSchema[WorkGroupSchema]:
    items = await service.work_group_manager.search(order_by=["order", "name"])
    return ListDataResponseSchema[WorkGroupSchema].create(
        list_data=[WorkGroupSchema.model_validate(i) for i in items],
    )


@work_router.get("/groups/{group_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_work_group(
    group_id: UUID,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[WorkGroupSchema]:
    item = await service.work_group_manager.get_by_id(group_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work group not found")
    return DataResponseSchema[WorkGroupSchema](data=WorkGroupSchema.model_validate(item))


@work_router.post("/groups", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_work_group(
    body: CreateWorkGroupRequest,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[WorkGroupSchema]:
    item = await service.work_group_manager.create(body.model_dump())
    return DataResponseSchema[WorkGroupSchema](data=WorkGroupSchema.model_validate(item))


@work_router.put("/groups/{group_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_work_group(
    group_id: UUID,
    body: UpdateWorkGroupRequest,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[WorkGroupSchema]:
    item = await service.work_group_manager.update_by_id(group_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work group not found")
    return DataResponseSchema[WorkGroupSchema](data=WorkGroupSchema.model_validate(item))


@work_router.delete("/groups/{group_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_work_group(
    group_id: UUID,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[dict]:
    await service.work_group_manager.delete_by_id(group_id)
    return DataResponseSchema[dict](data={"deleted": str(group_id)})


# ── WorkType ──────────────────────────────────────────────────────────────────


@work_router.get("/types", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_work_types(
    filters: WorkFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: WorkService = Depends(get_work_service),
) -> ListDataResponseSchema[WorkTypeSchema]:
    filter_data = filters.model_dump(exclude_none=True)
    search_text = filter_data.pop("search", None)
    items = await service.work_type_manager.search(search=search_text, order_by=["name"], **filter_data)
    total = await service.work_type_manager.count(search=search_text, **filter_data)
    return ListDataResponseSchema[WorkTypeSchema].create(
        list_data=[WorkTypeSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@work_router.get("/types/{work_type_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_work_type(
    work_type_id: UUID,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[WorkTypeSchema]:
    item = await service.work_type_manager.get_by_id(work_type_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work type not found")
    return DataResponseSchema[WorkTypeSchema](data=WorkTypeSchema.model_validate(item))


@work_router.post("/types", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_work_type(
    body: CreateWorkTypeRequest,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[WorkTypeSchema]:
    item = await service.work_type_manager.create(body.model_dump())
    return DataResponseSchema[WorkTypeSchema](data=WorkTypeSchema.model_validate(item))


@work_router.put("/types/{work_type_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_work_type(
    work_type_id: UUID,
    body: UpdateWorkTypeRequest,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[WorkTypeSchema]:
    item = await service.work_type_manager.update_by_id(work_type_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work type not found")
    return DataResponseSchema[WorkTypeSchema](data=WorkTypeSchema.model_validate(item))


@work_router.delete("/types/{work_type_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_work_type(
    work_type_id: UUID,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[dict]:
    await service.work_type_manager.delete_by_id(work_type_id)
    return DataResponseSchema[dict](data={"deleted": str(work_type_id)})


# ── TechSequence ──────────────────────────────────────────────────────────────


@work_router.get("/tech-sequence/{housing_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_tech_sequence(
    housing_id: UUID,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[TechSequenceSchema]:
    housing = await service.housing_manager.get_by_id(housing_id)
    if not housing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Housing not found")

    items = await service.tech_sequence_manager.search(housing_id=housing_id, order_by=["order"])
    return DataResponseSchema[TechSequenceSchema](
        data=TechSequenceSchema(
            housing_id=housing_id,
            housing_name=housing.name,
            sequence=[TechSequenceItemSchema.model_validate(i) for i in items],
        )
    )


@work_router.post("/tech-sequence", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_tech_sequence_item(
    body: CreateTechSequenceItemRequest,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[TechSequenceItemSchema]:
    item = await service.tech_sequence_manager.create(body.model_dump())
    return DataResponseSchema[TechSequenceItemSchema](data=TechSequenceItemSchema.model_validate(item))


@work_router.delete("/tech-sequence/{item_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_tech_sequence_item(
    item_id: UUID,
    service: WorkService = Depends(get_work_service),
) -> DataResponseSchema[dict]:
    await service.tech_sequence_manager.delete_by_id(item_id)
    return DataResponseSchema[dict](data={"deleted": str(item_id)})
