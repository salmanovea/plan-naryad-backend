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
    section_id: Optional[UUID] = None
    section_name: Optional[str] = None
    total_plan_items: int = 0
    total_work_facts: int = 0
    total_reconciliation_results: int = 0
    total_alerts: int = 0
    total_critical_alerts: int = 0
    # 0..1 fractions (same scale as reconciliation completion_ratio).
    completion_rate: Optional[Decimal] = None
    submission_rate: Optional[Decimal] = None


class DashboardFilters(HousingBaseFilters):
    section_id: Optional[UUID] = Query(None, description="Optional section filter within the housing")
    date_from: Optional[date] = Query(None, description="Period start (default: today-7d)")
    date_to: Optional[date] = Query(None, description="Period end (default: today)")


class DashboardSectionSchema(BaseModel):
    section_id: UUID
    section_name: str
    total_plan_items: int = 0
    total_work_facts: int = 0
    total_reconciliation_results: int = 0
    # 0..1 fractions (same scale as reconciliation completion_ratio).
    completion_rate: Optional[Decimal] = None
    submission_rate: Optional[Decimal] = None


class DashboardSectionsFilters(BaseModel):
    housing_id: UUID = Query(..., description="Housing to break down by section")
    date_from: Optional[date] = Query(None, description="Period start (default: today-7d)")
    date_to: Optional[date] = Query(None, description="Period end (default: today)")
