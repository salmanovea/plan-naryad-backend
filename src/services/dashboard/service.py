from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.models import managers
from src.services.common import BaseService


class DashboardService(BaseService):
    def __init__(self, db: AsyncSession):
        self.plan_item_manager = managers.PlanItemManager(db)
        self.work_fact_manager = managers.WorkFactManager(db)
        self.reconciliation_manager = managers.ReconciliationResultManager(db)
        self.daily_summary_manager = managers.DailySummaryManager(db)
        self.alert_manager = managers.AlertManager(db)
        self.housing_manager = managers.HousingManager(db)

    async def get_overview(
        self,
        date_from: date,
        date_to: date,
        housing_id: Optional[UUID] = None,
    ) -> dict:
        base_filters: dict = {"date__gte": date_from, "date__lte": date_to}
        if housing_id:
            base_filters["housing_id"] = housing_id

        total_plan_items = await self.plan_item_manager.count(**base_filters)
        total_work_facts = await self.work_fact_manager.count(**base_filters)
        total_reconciliation_results = await self.reconciliation_manager.count(**base_filters)
        total_alerts = await self.alert_manager.count(**base_filters)
        total_critical_alerts = await self.alert_manager.count(**base_filters, level="critical")

        summaries = await self.daily_summary_manager.search(**base_filters, order_by=["-date"])

        completion_rate: Optional[Decimal] = None
        submission_rate: Optional[Decimal] = None
        if summaries:
            completion_rate = Decimal(sum(float(s.completion_rate) for s in summaries) / len(summaries)).quantize(
                Decimal("0.01")
            )
            submission_rate = Decimal(sum(float(s.submission_rate) for s in summaries) / len(summaries)).quantize(
                Decimal("0.01")
            )

        housing_name: Optional[str] = None
        if housing_id:
            housing = await self.housing_manager.get_by_id(housing_id)
            if housing:
                housing_name = housing.name

        return {
            "date_from": date_from,
            "date_to": date_to,
            "housing_id": housing_id,
            "housing_name": housing_name,
            "total_plan_items": total_plan_items,
            "total_work_facts": total_work_facts,
            "total_reconciliation_results": total_reconciliation_results,
            "total_alerts": total_alerts,
            "total_critical_alerts": total_critical_alerts,
            "completion_rate": completion_rate,
            "submission_rate": submission_rate,
        }


async def get_dashboard_service(db: AsyncSession = Depends(get_session)) -> DashboardService:
    return DashboardService(db=db)
