from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemes import (
    DeleteMultipleRequestSchema,
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.plan.schemes import (
    AvailableWorkRow,
    DailyAssignmentRow,
    NamedRef,
    TransferPlanRequest,
    ConfirmPlanRequest,
    ContractorPlanResponse,
    CreatePlanItemRequest,
    DailyPlanResponse,
    GeneratePlanRequest,
    GeneratePlanResponse,
    PlanFilters,
    PlanItemSchema,
)
from src.services.common import current_actor
from src.services.plan.service import AutogenerationService, default_target_date, get_plan_service
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

    project_id = filter_data.pop("project_id", None)
    project_ids = filter_data.pop("project_id__in", None)
    if project_id or project_ids:
        housing_ids = await service.housings_of_projects([project_id] if project_id else project_ids)
        if not housing_ids:
            return ListDataResponseSchema[PlanItemSchema].create(list_data=[], pagination=pagination, total=0)
        filter_data["housing_id__in"] = housing_ids

    items, total = await service.list_plan_items(pagination=pagination, order_by=["-date"], **filter_data)
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
    section_id: UUID = Query(None, description="Optional section filter within the housing"),
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[DailyPlanResponse]:
    search_kwargs: dict = {"date": target_date, "housing_id": housing_id}
    if section_id:
        search_kwargs["section_id"] = section_id
    items = await service.get_plan_items(**search_kwargs)
    housing = await service.housing_manager.get_by_id(housing_id)
    return DataResponseSchema[DailyPlanResponse](
        data=DailyPlanResponse(
            date=target_date,
            housing_id=housing_id,
            housing_name=housing.name if housing else None,
            total_items=len(items),
            items=items,
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

    items = await service.get_plan_items(**filter_kwargs)
    contractor = await service.contractor_manager.get_by_id(contractor_id)
    return DataResponseSchema[ContractorPlanResponse](
        data=ContractorPlanResponse(
            date=target_date,
            contractor_id=contractor_id,
            contractor_name=contractor.name if contractor else None,
            housing_id=housing_id,
            items=items,
            total_items=len(items),
        )
    )


@plan_router.post("/generate", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def generate_plan(
    body: GeneratePlanRequest,
    service: AutogenerationService = Depends(get_plan_service),
    actor: str = Depends(current_actor),
) -> DataResponseSchema[GeneratePlanResponse]:
    target_date = body.date or default_target_date()

    if not body.force and await service.has_plan_for(body.housing_id, target_date, body.section_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "План-наряд на выбранную дату уже содержит позиции. При повторном запуске "
                "автогенерации текущий план-наряд будет сформирован заново, а все позиции, "
                "добавленные вручную, будут удалены. Продолжить?"
            ),
        )

    items, reasons = await service.generate_daily_plan(
        body.housing_id, target_date, body.section_id, force=body.force, actor=actor
    )
    if items:
        message = f"Сгенерировано позиций: {len(items)} на {target_date}."
    else:
        message = f"Не удалось сгенерировать план на {target_date}."
    return DataResponseSchema[GeneratePlanResponse](
        data=GeneratePlanResponse(
            items=[PlanItemSchema.model_validate(i) for i in items],
            count=len(items),
            message=message,
            reasons=reasons,
        )
    )


@plan_router.post("/bulk-confirm", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def bulk_confirm(
    body: DeleteMultipleRequestSchema,
    service: AutogenerationService = Depends(get_plan_service),
    actor: str = Depends(current_actor),
) -> DataResponseSchema[dict]:
    """Confirm the selected positions — a day holds ~136 of them, one by one is not a flow."""
    return DataResponseSchema[dict](data=await service.confirm_items(body.ids, actor=actor))


@plan_router.post("/bulk-delete", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def bulk_delete(
    body: DeleteMultipleRequestSchema,
    service: AutogenerationService = Depends(get_plan_service),
    actor: str = Depends(current_actor),
) -> DataResponseSchema[dict]:
    """Delete the selected positions."""
    return DataResponseSchema[dict](data=await service.delete_items(body.ids, actor=actor))


@plan_router.get("/daily-assignment", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def daily_assignment(
    housing_raport_id: str = Query(..., description="Raport housing id"),
    target_date: date = Query(..., alias="date", description="Day the assignment is for"),
    section_raport_id: str | None = Query(None, description="Raport section id, for the per-section view"),
    service: AutogenerationService = Depends(get_plan_service),
) -> ListDataResponseSchema[DailyAssignmentRow]:
    """Cells to keep active in Raport's «Задание на день» view.

    Consumed by Raport, so both input and output speak Raport ids. Only positions already
    handed to the contractors (`transferred`) are returned; an empty list means the toggle
    should stay inactive.
    """
    rows = await service.daily_assignment(
        housing_raport_id=housing_raport_id,
        target_date=target_date,
        section_raport_id=section_raport_id,
    )
    return ListDataResponseSchema[DailyAssignmentRow].create(
        list_data=[DailyAssignmentRow.model_validate(r) for r in rows]
    )


@plan_router.post("/transfer", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def transfer_plan(
    body: TransferPlanRequest,
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[dict]:
    """Hand the day's positions to the contractors.

    After the cutoff every position that was not deleted goes over, confirmed or not — the
    spec is explicit about that. Called by the scheduler; exposed for debugging too.
    """
    result = await service.transfer_day(body.date, housing_id=body.housing_id, section_id=body.section_id)
    return DataResponseSchema[dict](data=result)


@plan_router.get("/available-works", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def available_works(
    housing_id: UUID = Query(..., description="Housing the floor belongs to"),
    section_id: UUID = Query(..., description="Section the floor belongs to"),
    floor_id: UUID = Query(..., description="Floor the work has to apply to"),
    service: AutogenerationService = Depends(get_plan_service),
) -> ListDataResponseSchema[AvailableWorkRow]:
    """Works offerable in the manual-add dialog, as the four-level tree.

    Scoped to the section's own calendar plan when it has one, then to the works Raport's
    chessboard actually has on that floor. When Raport cannot answer, the wider list is
    returned rather than an empty one.
    """
    rows = await service.available_works(housing_id=housing_id, section_id=section_id, floor_id=floor_id)
    return ListDataResponseSchema[AvailableWorkRow].create(list_data=[AvailableWorkRow.model_validate(r) for r in rows])


@plan_router.get("/available-contractors", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def available_contractors(
    work_id: UUID = Query(..., description="Work to be assigned"),
    floor_id: UUID = Query(..., description="Floor the work runs on"),
    service: AutogenerationService = Depends(get_plan_service),
) -> ListDataResponseSchema[NamedRef]:
    """Contractors assigned to this work on this floor, read live from Raport."""
    rows = await service.available_contractors(work_id=work_id, floor_id=floor_id)
    return ListDataResponseSchema[NamedRef].create(list_data=[NamedRef.model_validate(r) for r in rows])


@plan_router.post("/", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_plan_item(
    body: CreatePlanItemRequest,
    service: AutogenerationService = Depends(get_plan_service),
    actor: str = Depends(current_actor),
) -> DataResponseSchema[PlanItemSchema]:
    """Add a position by hand — outside the technological sequence is allowed by the spec,
    an unassigned contractor is not."""
    item, error = await service.add_manual_item(
        housing_id=body.housing_id,
        section_id=body.section_id,
        floor_id=body.floor_id,
        work_id=body.work_id,
        contractor_id=body.contractor_id,
        target_date=body.date,
        actor=actor,
    )
    if error or item is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return DataResponseSchema[PlanItemSchema](data=PlanItemSchema.model_validate(item))


@plan_router.get("/{plan_item_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_plan_item(
    plan_item_id: UUID,
    service: AutogenerationService = Depends(get_plan_service),
) -> DataResponseSchema[PlanItemSchema]:
    item = await service.get_plan_item(plan_item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan item not found")
    return DataResponseSchema[PlanItemSchema](data=item)


@plan_router.post("/{plan_item_id}/confirm", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def confirm_plan_item(
    plan_item_id: UUID,
    body: ConfirmPlanRequest,
    service: AutogenerationService = Depends(get_plan_service),
    actor: str = Depends(current_actor),
) -> DataResponseSchema[PlanItemSchema]:
    item = await service.confirm_item(plan_item_id, actor=actor)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan item not found")
    return DataResponseSchema[PlanItemSchema](data=PlanItemSchema.model_validate(item))


@plan_router.delete("/{plan_item_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_plan_item(
    plan_item_id: UUID,
    service: AutogenerationService = Depends(get_plan_service),
    actor: str = Depends(current_actor),
) -> DataResponseSchema[dict]:
    if not await service.delete_item(plan_item_id, actor=actor):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan item not found")
    return DataResponseSchema[dict](data={"deleted": str(plan_item_id)})
