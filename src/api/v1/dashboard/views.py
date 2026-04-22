from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from src.api.schemes import (
    DataResponseSchema,
    ResponseGroup,
)
from src.api.v1.dashboard.schemes import DashboardFilters, DashboardOverviewSchema
from src.services.dashboard.service import DashboardService, get_dashboard_service
from src.utils.helpers import catch_all_exceptions, get_responses

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@dashboard_router.get("/overview", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_dashboard_overview(
    filters: DashboardFilters = Depends(),
    service: DashboardService = Depends(get_dashboard_service),
) -> DataResponseSchema[DashboardOverviewSchema]:
    date_from = filters.date_from or date.today() - timedelta(days=7)
    date_to = filters.date_to or date.today()

    overview = await service.get_overview(
        date_from=date_from,
        date_to=date_to,
        housing_id=filters.housing_id,
    )
    return DataResponseSchema[DashboardOverviewSchema](
        data=DashboardOverviewSchema(**overview)
    )
