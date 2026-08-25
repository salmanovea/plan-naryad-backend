from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo.tables.reconciliation import ReconciliationStatus
from src.services.common import BaseService


class DashboardService(BaseService):
    def __init__(self, db: AsyncSession):
        self.plan_item_manager = managers.PlanItemManager(db)
        self.work_fact_manager = managers.WorkFactManager(db)
        self.reconciliation_manager = managers.ReconciliationResultManager(db)
        self.daily_summary_manager = managers.DailySummaryManager(db)
        self.alert_manager = managers.AlertManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)

    async def _completion_rates(self, **recon_filters) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """Compute (completion_rate, submission_rate) as 0..1 fractions.

        Derived directly from reconciliation_results so the figures honour the
        section filter (daily_summaries are housing-level only). completion_rate =
        (DONE_FULL + DONE_OVER) / planned; submission_rate = (planned - NO_REPORT)
        / planned, where `planned` counts rows tied to a plan item.
        """
        planned = await self.reconciliation_manager.count(**recon_filters, plan_item_id__isnotnull=True)
        if not planned:
            return None, None

        done = await self.reconciliation_manager.count(
            **recon_filters,
            plan_item_id__isnotnull=True,
            status__in=[ReconciliationStatus.DONE_FULL, ReconciliationStatus.DONE_OVER],
        )
        no_report = await self.reconciliation_manager.count(
            **recon_filters,
            plan_item_id__isnotnull=True,
            status=ReconciliationStatus.NO_REPORT,
        )
        quant = Decimal("0.0001")
        completion_rate = (Decimal(done) / Decimal(planned)).quantize(quant)
        submission_rate = (Decimal(planned - no_report) / Decimal(planned)).quantize(quant)
        return completion_rate, submission_rate

    async def get_overview(
        self,
        date_from: date,
        date_to: date,
        housing_id: Optional[UUID] = None,
        section_id: Optional[UUID] = None,
    ) -> dict:
        # Filters for entities that carry section_id (plan items, facts, results).
        scoped_filters: dict = {"date__gte": date_from, "date__lte": date_to}
        if housing_id:
            scoped_filters["housing_id"] = housing_id
        if section_id:
            scoped_filters["section_id"] = section_id

        fact_filters: dict = dict(scoped_filters)
        fact_filters["work_date__gte"] = fact_filters.pop("date__gte")
        fact_filters["work_date__lte"] = fact_filters.pop("date__lte")

        # Alerts have no section_id column — they stay at housing granularity.
        alert_filters: dict = {"date__gte": date_from, "date__lte": date_to}
        if housing_id:
            alert_filters["housing_id"] = housing_id

        total_plan_items = await self.plan_item_manager.count(**scoped_filters)
        total_work_facts = await self.work_fact_manager.count(**fact_filters)
        total_reconciliation_results = await self.reconciliation_manager.count(**scoped_filters)
        total_alerts = await self.alert_manager.count(**alert_filters)
        total_critical_alerts = await self.alert_manager.count(**alert_filters, level="critical")

        completion_rate, submission_rate = await self._completion_rates(**scoped_filters)

        housing_name: Optional[str] = None
        if housing_id:
            housing = await self.housing_manager.get_by_id(housing_id)
            if housing:
                housing_name = housing.name

        section_name: Optional[str] = None
        if section_id:
            section = await self.section_manager.get_by_id(section_id)
            if section:
                section_name = section.name

        return {
            "date_from": date_from,
            "date_to": date_to,
            "housing_id": housing_id,
            "housing_name": housing_name,
            "section_id": section_id,
            "section_name": section_name,
            "total_plan_items": total_plan_items,
            "total_work_facts": total_work_facts,
            "total_reconciliation_results": total_reconciliation_results,
            "total_alerts": total_alerts,
            "total_critical_alerts": total_critical_alerts,
            "completion_rate": completion_rate,
            "submission_rate": submission_rate,
        }

    async def get_sections_overview(
        self,
        housing_id: UUID,
        date_from: date,
        date_to: date,
    ) -> list[dict]:
        """Per-section KPI breakdown for one housing.

        One row per section of the housing, ordered by section_number. Alert
        counts are intentionally absent — alerts have no section granularity.
        """
        sections = await self.section_manager.search(housing_id=housing_id, order_by=["section_number"])
        rows: list[dict] = []
        for section in sections:
            scoped: dict = {
                "date__gte": date_from,
                "date__lte": date_to,
                "housing_id": housing_id,
                "section_id": section.id,
            }
            fact_scoped: dict = dict(scoped)
            fact_scoped["work_date__gte"] = fact_scoped.pop("date__gte")
            fact_scoped["work_date__lte"] = fact_scoped.pop("date__lte")

            completion_rate, submission_rate = await self._completion_rates(**scoped)
            rows.append(
                {
                    "section_id": section.id,
                    "section_name": section.name,
                    "total_plan_items": await self.plan_item_manager.count(**scoped),
                    "total_work_facts": await self.work_fact_manager.count(**fact_scoped),
                    "total_reconciliation_results": await self.reconciliation_manager.count(**scoped),
                    "completion_rate": completion_rate,
                    "submission_rate": submission_rate,
                }
            )
        return rows


async def get_dashboard_service(db: AsyncSession = Depends(get_session)) -> DashboardService:
    return DashboardService(db=db)
