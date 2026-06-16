from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    PaginationParams,
    ResponseGroup,
)
from src.api.v1.alert.schemes import (
    AcknowledgeAlertRequest,
    AlertFilters,
    AlertSchema,
    EscalationCheckResponse,
    GenerateAlertsRequest,
    GenerateAlertsResponse,
)
from src.services.alert.service import AlertService, get_alert_service
from src.utils.helpers import catch_all_exceptions, get_responses, pagination_params

alert_router = APIRouter(prefix="/alerts", tags=["Alerts"])


@alert_router.get("/", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_alerts(
    filters: AlertFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: AlertService = Depends(get_alert_service),
) -> ListDataResponseSchema[AlertSchema]:
    filter_data = filters.model_dump(exclude_none=True)
    date_from = filter_data.pop("date_from", None)
    date_to = filter_data.pop("date_to", None)
    if date_from:
        filter_data["date__gte"] = date_from
    if date_to:
        filter_data["date__lte"] = date_to

    items, total = await service.list_alerts(pagination=pagination, order_by=["-date"], **filter_data)
    return ListDataResponseSchema[AlertSchema].create(
        list_data=[AlertSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@alert_router.get("/{alert_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_alert(
    alert_id: UUID,
    service: AlertService = Depends(get_alert_service),
) -> DataResponseSchema[AlertSchema]:
    item = await service.get_alert(alert_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return DataResponseSchema[AlertSchema](data=item)


@alert_router.post("/generate", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def generate_alerts(
    body: GenerateAlertsRequest,
    service: AlertService = Depends(get_alert_service),
) -> DataResponseSchema[GenerateAlertsResponse]:
    created = await service.generate_daily_alerts(body.housing_id, body.alert_date)
    return DataResponseSchema[GenerateAlertsResponse](
        data=GenerateAlertsResponse(
            generated=len(created),
            alerts=[AlertSchema.model_validate(a) for a in created],
        )
    )


@alert_router.post("/{alert_id}/acknowledge", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def acknowledge_alert(
    alert_id: UUID,
    body: AcknowledgeAlertRequest,
    service: AlertService = Depends(get_alert_service),
) -> DataResponseSchema[AlertSchema]:
    alert = await service.acknowledge_alert(alert_id, body.acknowledged_by)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    updated = await service.get_alert(alert_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return DataResponseSchema[AlertSchema](data=updated)


@alert_router.post("/escalation/run", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def run_escalation_check(
    service: AlertService = Depends(get_alert_service),
) -> DataResponseSchema[EscalationCheckResponse]:
    count = await service.run_escalation_check()
    return DataResponseSchema[EscalationCheckResponse](data=EscalationCheckResponse(escalated_count=count))
