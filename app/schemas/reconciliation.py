from pydantic import BaseModel
from datetime import date, datetime
from uuid import UUID
from typing import Optional, Any
from decimal import Decimal
from enum import Enum

class CompletionStatus(str, Enum):
    DONE_FULL = "DONE_FULL"
    DONE_PARTIAL = "DONE_PARTIAL" 
    DONE_OVER = "DONE_OVER"
    NOT_DONE = "NOT_DONE"
    NO_REPORT = "NO_REPORT"
    UNPLANNED = "UNPLANNED"

class ReconciliationResultBase(BaseModel):
    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_type_id: UUID
    contractor_id: UUID
    planned_volume: Optional[Decimal] = None
    actual_volume: Optional[Decimal] = None
    completion_ratio: Optional[Decimal] = None
    status: CompletionStatus
    pattern: Optional[str] = None

class ReconciliationResult(ReconciliationResultBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class ReconciliationResultWithDetails(ReconciliationResult):
    housing_name: Optional[str] = None
    section_name: Optional[str] = None
    floor_name: Optional[str] = None
    work_name: Optional[str] = None
    contractor_name: Optional[str] = None

class DailySummaryBase(BaseModel):
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

class DailySummary(DailySummaryBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class DailySummaryWithDetails(DailySummary):
    housing_name: Optional[str] = None

class ReconciliationRun(BaseModel):
    date: date
    housing_id: Optional[UUID] = None

class ReconciliationStats(BaseModel):
    start_date: date
    end_date: date
    total_results: int
    by_status: dict
    by_housing: dict
    completion_rate: Decimal
    weighted_completion: Decimal
    submission_rate: Decimal
