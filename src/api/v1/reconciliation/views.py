from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.reconciliation.schemes import (
    DailySummarySchema,
    ReconciliationFilterOptions,
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
    result = await service.run_reconciliation(
        date_from=body.date_from,
        date_to=body.date_to,
        housing_id=body.housing_id,
        project_id=body.project_id,
    )
    return DataResponseSchema[ReconciliationRunResponse](data=ReconciliationRunResponse(**result))


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

    project_id = filter_data.pop("project_id", None)
    project_ids = filter_data.pop("project_id__in", None)
    if project_id or project_ids:
        housing_ids = await service._housings_in_scope(None, project_id) if project_id else []
        if project_ids:
            for pid in project_ids:
                housing_ids += await service._housings_in_scope(None, pid)
        if not housing_ids:
            filter_data["housing_id__in"] = [UUID(int=0)]
        else:
            filter_data["housing_id__in"] = housing_ids

    items, total = await service.list_results(pagination=pagination, order_by=["-date"], **filter_data)
    return ListDataResponseSchema[ReconciliationResultSchema].create(
        list_data=[ReconciliationResultSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@reconciliation_router.get("/filter-options", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def reconciliation_filter_options(
    housing_id: UUID | None = Query(None, description="Housing the table is scoped to"),
    project_id: UUID | None = Query(None, description="Project, when no single housing is chosen"),
    date_from: date | None = Query(None, description="Start of the reconciled range (inclusive)"),
    date_to: date | None = Query(None, description="End of the reconciled range (inclusive)"),
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> DataResponseSchema[ReconciliationFilterOptions]:
    """Values present in the scope, per filterable column.

    The results table is paginated on the server, so its column filters cannot be assembled
    from the rows the browser holds.
    """
    options = await service.filter_options(
        housing_id=housing_id,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
    )
    return DataResponseSchema[ReconciliationFilterOptions](data=ReconciliationFilterOptions.model_validate(options))


@reconciliation_router.get("/results/{result_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_reconciliation_result(
    result_id: UUID,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> DataResponseSchema[ReconciliationResultSchema]:
    item = await service.get_result(result_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reconciliation result not found")
    return DataResponseSchema[ReconciliationResultSchema](data=item)


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
    summary_filters = {key: filter_data[key] for key in ("housing_id", "housing_id__in") if key in filter_data}
    if date_from:
        summary_filters["date__gte"] = date_from
    if date_to:
        summary_filters["date__lte"] = date_to

    items, total = await service.list_summaries(
        pagination=pagination,
        order_by=["-date"],
        project_id=filter_data.get("project_id"),
        **summary_filters,
    )
    return ListDataResponseSchema[DailySummarySchema].create(
        list_data=items,
        pagination=pagination,
        total=total,
    )


@reconciliation_router.get("/summaries/{summary_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_daily_summary(
    summary_id: UUID,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> DataResponseSchema[DailySummarySchema]:
    item = await service.get_summary(summary_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily summary not found")
    return DataResponseSchema[DailySummarySchema](data=item)
