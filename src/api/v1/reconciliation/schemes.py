from datetime import date as date_type
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from src.api.schemes import (
    ContractorBaseFilters,
    FloorBaseFilters,
    HousingBaseFilters,
    IDMixinSchema,
    ProjectBaseFilters,
    SectionBaseFilters,
    WorkBaseFilters,
)
from src.models.dbo.tables.reconciliation import ReconciliationPattern, ReconciliationStatus


class RunReconciliationRequest(BaseModel):
    """The «Запустить сверку» button: project, housing and a date range (ТЗ)."""

    date_from: date_type
    date_to: Optional[date_type] = None
    housing_id: Optional[UUID] = None
    project_id: Optional[UUID] = None


class ReconciliationResultSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_id: UUID
    contractor_id: UUID
    source_percent: Optional[Decimal] = None
    fact_percent: Optional[Decimal] = None
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
    floor_number: Optional[int] = None
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
    date_from: date_type
    date_to: date_type
    housing_count: int
    total_results: int
    total_summaries: int


class FilterRef(BaseModel):
    """One option of a column filter."""

    id: UUID
    name: str


class FloorFilterRef(FilterRef):
    """A floor option, kept under its section — the floor filter is a «Секция → Этаж» tree."""

    section_id: UUID
    floor_number: Optional[int] = None


class WorkFilterRef(FilterRef):
    """A work option with its catalogue chain, for the «Этап → Комплекс → Вид → Работа» tree."""

    work_type_name: Optional[str] = None
    work_group_name: Optional[str] = None
    work_set_name: Optional[str] = None


class ReconciliationFilterOptions(BaseModel):
    """Values actually present in the reconciled scope, per column.

    The table is paginated on the server (a month over one housing runs into thousands of
    rows), so a column filter cannot be built from the page in the browser — it would offer
    only what happens to be visible.
    """

    statuses: List[str] = []
    patterns: List[str] = []
    works: List[WorkFilterRef] = []
    sections: List[FilterRef] = []
    floors: List[FloorFilterRef] = []
    contractors: List[FilterRef] = []


class ReconciliationFilters(
    HousingBaseFilters,
    SectionBaseFilters,
    FloorBaseFilters,
    WorkBaseFilters,
    ContractorBaseFilters,
    ProjectBaseFilters,
):
    """Table filters: the spec wants multi-select with «select all» on every column."""

    date_from: Optional[date_type] = Query(None, description="Filter by date from (inclusive)")
    date_to: Optional[date_type] = Query(None, description="Filter by date to (inclusive)")
    status: Optional[ReconciliationStatus] = Query(None, description="Filter by reconciliation status")
    status__in: Optional[List[ReconciliationStatus]] = Field(Query(None, description="Filter by several statuses"))
    pattern__in: Optional[List[str]] = Field(Query(None, description="Filter by several patterns"))
