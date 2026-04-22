from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.plan.schemes import (
    AdjustPlanRequest,
    ConfirmPlanRequest,
    ContractorPlanResponse,
    CreatePlanItemRequest,
    DailyPlanResponse,
    GeneratePlanRequest,
    GeneratePlanResponse,
    PlanFilters,
    PlanItemSchema,
)
from src.services.plan.service import AutogenerationService, get_plan_service
from src.utils.helpers import catch_all_exceptions, get_responses, pagination_params

plan_router = APIRouter(prefix="/plan-naryad", tags=["Plan Naryad"])


@plan_router.get("/", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_plan_items(
    filters: PlanFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: AutogenerationService = Depends(get_plan_service),
) -> ListDataResponseSchema[PlanItemSchema]:
    filter_data = filters.model_dump(exclude_none=True)
    date_from = filter_data.pop("date_from", None)
    date_to = filter_data.pop("date_to", None)
    if date_from:
        filter_data["date__gte"] = date_from
    if date_to:
        filter_data["date__lte"] = date_to

    items = await service.plan_item_manager.search(order_by=["-date"], **filter_data)
    total = await service.plan_item_manager.count(**filter_data)
    return ListDataResponseSchema[PlanItemSchema].create(
        list_data=[PlanItemSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@plan_router.get("/daily", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_daily_plan(
    target_date: date = Query(..., description="Date to get plan for"),
    housing_id: UUID = Query(..., description="Housing ID"),
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[DailyPlanResponse]:
    items = await service.plan_item_manager.search(date=target_date, housing_id=housing_id)
    housing = await service.housing_manager.get_by_id(housing_id)
    return DataResponseSchema[DailyPlanResponse](
        data=DailyPlanResponse(
            date=target_date,
            housing_id=housing_id,
            housing_name=housing.name if housing else None,
            total_items=len(items),
            items=[PlanItemSchema.model_validate(i) for i in items],
        )
    )


@plan_router.get("/contractor", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_contractor_plan(
    target_date: date = Query(..., description="Date to get plan for"),
    contractor_id: UUID = Query(..., description="Contractor ID"),
    housing_id: UUID = Query(None, description="Housing ID filter"),
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[ContractorPlanResponse]:
    filter_kwargs: dict = {"date": target_date, "contractor_id": contractor_id}
    if housing_id:
        filter_kwargs["housing_id"] = housing_id

    items = await service.plan_item_manager.search(**filter_kwargs)
    contractor = await service.contractor_manager.get_by_id(contractor_id)
    return DataResponseSchema[ContractorPlanResponse](
        data=ContractorPlanResponse(
            date=target_date,
            contractor_id=contractor_id,
            contractor_name=contractor.name if contractor else None,
            housing_id=housing_id,
            items=[PlanItemSchema.model_validate(i) for i in items],
            total_items=len(items),
        )
    )


@plan_router.post("/generate", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def generate_plan(
    body: GeneratePlanRequest,
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[GeneratePlanResponse]:
    items = await service.generate_daily_plan(body.housing_id, body.date)
    return DataResponseSchema[GeneratePlanResponse](
        data=GeneratePlanResponse(
            items=[PlanItemSchema.model_validate(i) for i in items],
            count=len(items),
            message=f"Generated {len(items)} plan items for {body.date}",
        )
    )


@plan_router.post("/", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_plan_item(
    body: CreatePlanItemRequest,
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[PlanItemSchema]:
    item = await service.plan_item_manager.create(body.model_dump())
    return DataResponseSchema[PlanItemSchema](data=PlanItemSchema.model_validate(item))


@plan_router.get("/{plan_item_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_plan_item(
    plan_item_id: UUID,
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[PlanItemSchema]:
    item = await service.plan_item_manager.get_by_id(plan_item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan item not found")
    return DataResponseSchema[PlanItemSchema](data=PlanItemSchema.model_validate(item))


@plan_router.post("/{plan_item_id}/confirm", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def confirm_plan_item(
    plan_item_id: UUID,
    body: ConfirmPlanRequest,
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[PlanItemSchema]:
    item = await service.plan_item_manager.update_by_id(
        plan_item_id,
        {"rs_confirmed": True, "status": "confirmed"},
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan item not found")
    return DataResponseSchema[PlanItemSchema](data=PlanItemSchema.model_validate(item))


@plan_router.post("/{plan_item_id}/adjust", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def adjust_plan_item(
    plan_item_id: UUID,
    body: AdjustPlanRequest,
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[PlanItemSchema]:
    update_data = {change.field: change.new_value for change in body.changes}
    item = await service.plan_item_manager.update_by_id(plan_item_id, update_data)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan item not found")

    await service.plan_adjustment_manager.create(
        {
            "plan_item_id": plan_item_id,
            "reason": body.reason,
            "adjusted_by": body.adjusted_by,
            "changes": [c.model_dump() for c in body.changes],
        },
        commit=True,
    )

    return DataResponseSchema[PlanItemSchema](data=PlanItemSchema.model_validate(item))


@plan_router.delete("/{plan_item_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_plan_item(
    plan_item_id: UUID,
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[dict]:
    await service.plan_item_manager.delete_by_id(plan_item_id)
    return DataResponseSchema[dict](data={"deleted": str(plan_item_id)})
