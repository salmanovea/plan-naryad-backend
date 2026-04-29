from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel

from src.api.schemes import HousingBaseFilters


class DashboardOverviewSchema(BaseModel):
    date_from: date
    date_to: date
    housing_id: Optional[UUID] = None
    housing_name: Optional[str] = None
    total_plan_items: int = 0
    total_work_facts: int = 0
    total_reconciliation_results: int = 0
    total_alerts: int = 0
    total_critical_alerts: int = 0
    completion_rate: Optional[Decimal] = None
    submission_rate: Optional[Decimal] = None


class DashboardFilters(HousingBaseFilters):
    date_from: Optional[date] = Query(None, description="Period start (default: today-7d)")
    date_to: Optional[date] = Query(None, description="Period end (default: today)")
