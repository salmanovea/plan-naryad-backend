"""Domain DTOs for the workforce service (not API response schemas)."""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WfProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    project_class: str
    description: Optional[str] = None


class WorkTypeRow(BaseModel):
    work_type: str
    bdr_amount: Decimal
    management_completion_amount: Decimal
    uv_pct: float
    net_bdr: Decimal
    norm_day: Optional[Decimal]
    required_headcount: Optional[float]
    plan_report: Optional[int] = None
    fact_30d: float
    fact_7d: float
    coverage_pct: Optional[float]
    coverage_report_pct: Optional[float] = None
    trend: str
    traffic_light: str
    traffic_light_report: str = "grey"


class ObjectDashboardItem(BaseModel):
    id: UUID
    name: str
    net_bdr: Decimal
    required_headcount: Optional[float]
    plan_report: Optional[int]
    fact_30d: float
    fact_7d: float
    coverage_pct: Optional[float]
    coverage_report_pct: Optional[float]
    trend: str
    traffic_light: str
    traffic_light_report: str
    top_problem: Optional[str]
    work_types: List[WorkTypeRow]


class ProjectRow(BaseModel):
    id: UUID
    name: str
    project_class: str
    net_bdr: Decimal
    required_headcount: Optional[float]
    fact_30d: float
    coverage_pct: Optional[float]
    trend: str
    top_problem: Optional[str]
    traffic_light: str


class DashboardResponse(BaseModel):
    total_net_bdr: Decimal
    total_required: Optional[float]
    total_fact_30d: float
    portfolio_coverage_pct: Optional[float]
    projects: List[ProjectRow]


class ProjectDetailResponse(BaseModel):
    project: WfProjectOut
    period_month: Optional[date]
    net_bdr: Optional[Decimal] = None
    required_headcount: Optional[float] = None
    plan_report: Optional[int] = None
    fact_30d: Optional[float] = None
    fact_7d: Optional[float] = None
    coverage_pct: Optional[float] = None
    coverage_report_pct: Optional[float] = None
    trend: Optional[str] = None
    traffic_light: Optional[str] = None
    traffic_light_report: Optional[str] = None
    objects: List[ObjectDashboardItem] = []
    work_types: List[WorkTypeRow] = []


class ForecastRow(BaseModel):
    object_id: UUID
    object_name: str
    work_type: str
    remaining_amount: Optional[Decimal]
    planned_end_date: Optional[date]
    fact_30d: float
    norm_month: Optional[float]
    months_needed: Optional[float]
    forecast_date: Optional[date]
    delay_months: Optional[float]


class ForecastResponse(BaseModel):
    project_id: UUID
    rows: List[ForecastRow]


class ContractorHeadcountRow(BaseModel):
    contractor_id: Optional[UUID]
    contractor_name: str
    work_type: str
    plan: Optional[int]
    fact_30d: float
    coverage_pct: Optional[float]


class SystemProblemRow(BaseModel):
    work_type: str
    affected_objects: int
    avg_coverage_pct: Optional[float]
    object_names: List[str]


class SystemProblemsResponse(BaseModel):
    threshold_pct: float
    min_objects: int
    problems: List[SystemProblemRow]


class ContractorRatingRow(BaseModel):
    contractor_id: UUID
    contractor_name: str
    avg_coverage_pct: Optional[float]
    violation_count: int
    missed_checkpoints: int
    rating_score: float


class ViolationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    object_id: UUID
    work_type: str
    contractor_id: Optional[UUID] = None
    violation_date: date
    violation_type: str
    description: str
    plan_count: int
    fact_count: int
    escalated: bool
    escalated_to: Optional[str] = None
    resolved: bool
    project_name: Optional[str] = None
    object_name: Optional[str] = None
    contractor_name: Optional[str] = None


class ViolationScanResult(BaseModel):
    created: int
    violations: List[ViolationOut]
