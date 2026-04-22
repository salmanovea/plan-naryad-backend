from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.reconciliation.schemes import (
    DailySummarySchema,
    ReconciliationFilters,
    ReconciliationResultSchema,
    ReconciliationRunResponse,
    RunReconciliationRequest,
)
from src.services.reconciliation.service import ReconciliationService, get_reconciliation_service
from src.utils.helpers import catch_all_exceptions, get_responses, pagination_params

reconciliation_router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


@reconciliation_router.post("/run", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def run_reconciliation(
    body: RunReconciliationRequest,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> DataResponseSchema[ReconciliationRunResponse]:
    result = await service.run_reconciliation(body.date, body.housing_id)
    return DataResponseSchema[ReconciliationRunResponse](
        data=ReconciliationRunResponse(**result)
    )


@reconciliation_router.get("/results", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_reconciliation_results(
    filters: ReconciliationFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> ListDataResponseSchema[ReconciliationResultSchema]:
    filter_data = filters.model_dump(exclude_none=True)
    date_from = filter_data.pop("date_from", None)
    date_to = filter_data.pop("date_to", None)
    if date_from:
        filter_data["date__gte"] = date_from
    if date_to:
        filter_data["date__lte"] = date_to

    items = await service.reconciliation_manager.search(order_by=["-date"], **filter_data)
    total = await service.reconciliation_manager.count(**filter_data)
    return ListDataResponseSchema[ReconciliationResultSchema].create(
        list_data=[ReconciliationResultSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@reconciliation_router.get(
    "/results/{result_id}", responses=get_responses(ResponseGroup.ALL_ERRORS)
)
@catch_all_exceptions
async def get_reconciliation_result(
    result_id: UUID,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> DataResponseSchema[ReconciliationResultSchema]:
    item = await service.reconciliation_manager.get_by_id(result_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reconciliation result not found"
        )
    return DataResponseSchema[ReconciliationResultSchema](
        data=ReconciliationResultSchema.model_validate(item)
    )


@reconciliation_router.get("/summaries", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_daily_summaries(
    filters: ReconciliationFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> ListDataResponseSchema[DailySummarySchema]:
    filter_data = filters.model_dump(exclude_none=True)
    date_from = filter_data.pop("date_from", None)
    date_to = filter_data.pop("date_to", None)
    filter_data.pop("status", None)
    if date_from:
        filter_data["date__gte"] = date_from
    if date_to:
        filter_data["date__lte"] = date_to

    items = await service.daily_summary_manager.search(order_by=["-date"], **filter_data)
    total = await service.daily_summary_manager.count(**filter_data)
    return ListDataResponseSchema[DailySummarySchema].create(
        list_data=[DailySummarySchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@reconciliation_router.get(
    "/summaries/{summary_id}", responses=get_responses(ResponseGroup.ALL_ERRORS)
)
@catch_all_exceptions
async def get_daily_summary(
    summary_id: UUID,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> DataResponseSchema[DailySummarySchema]:
    item = await service.daily_summary_manager.get_by_id(summary_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Daily summary not found"
        )
    return DataResponseSchema[DailySummarySchema](data=DailySummarySchema.model_validate(item))
