from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import HousingBaseFilters, IDMixinSchema
from src.models.dbo.tables.reconciliation import ReconciliationPattern, ReconciliationStatus


class RunReconciliationRequest(BaseModel):
    date: date
    housing_id: Optional[UUID] = None


class ReconciliationResultSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_type_id: UUID
    contractor_id: UUID
    planned_volume: Optional[Decimal] = None
    actual_volume: Optional[Decimal] = None
    completion_ratio: Optional[Decimal] = None
    status: ReconciliationStatus
    pattern: Optional[ReconciliationPattern] = None
    plan_item_id: Optional[UUID] = None
    work_fact_id: Optional[UUID] = None
    fact_is_late: bool = False
    # enriched
    housing_name: Optional[str] = None
    section_name: Optional[str] = None
    floor_name: Optional[str] = None
    work_name: Optional[str] = None
    contractor_name: Optional[str] = None


class DailySummarySchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    date: date
    housing_id: UUID
    total_planned: int
    total_done_full: int
    total_done_partial: int
    total_done_over: int
    total_not_done: int
    total_no_report: int
    total_unplanned: int
    completion_rate: Decimal
    weighted_completion: Decimal
    submission_rate: Decimal
    contractor_details: Optional[Any] = None
    alerts: Optional[Any] = None
    # enriched
    housing_name: Optional[str] = None


class ReconciliationRunResponse(BaseModel):
    date: date
    housing_count: int
    total_results: int
    total_summaries: int


class ReconciliationFilters(HousingBaseFilters):
    date_from: Optional[date] = Query(None, description="Filter by date from (inclusive)")
    date_to: Optional[date] = Query(None, description="Filter by date to (inclusive)")
    status: Optional[ReconciliationStatus] = Query(None, description="Filter by reconciliation status")
