"""
Pydantic-схемы для модуля управления численностью.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.workforce import ProjectClass, HeadcountSource, ChallengeStatus, ViolationType


# ── Project ──────────────────────────────────────────────────────────────────

class ProjectBase(BaseModel):
    name: str
    project_class: ProjectClass = ProjectClass.COMFORT
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


# ── ProjectObject ─────────────────────────────────────────────────────────────

class ProjectObjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectObjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    name: str
    description: Optional[str] = None
    planned_end_date: Optional[date] = None
    total_budget_remaining: Optional[Decimal] = None


# ── WorkforceNorm ─────────────────────────────────────────────────────────────

class NormBase(BaseModel):
    work_type: str
    project_class: ProjectClass
    median_day_bdr: Decimal
    median_month_bdr: Decimal
    q1: Optional[Decimal] = None
    q3: Optional[Decimal] = None
    count: Optional[int] = None


class NormCreate(NormBase):
    pass


class NormOut(NormBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


# ── BudgetItem / BudgetPeriod ─────────────────────────────────────────────────

class BudgetItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    work_type: str
    detailed_article: Optional[str] = None
    bdr_amount: Decimal
    management_completion_amount: Decimal
    object_id: Optional[UUID] = None
    contractor_id: Optional[UUID] = None
    remaining_amount: Optional[Decimal] = None
    planned_end_date: Optional[date] = None


# ── ArticleMapping ────────────────────────────────────────────────────────────

class ArticleMappingCreate(BaseModel):
    article_code: str
    article_label: str
    work_type: str


class ArticleMappingOut(ArticleMappingCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ArticleMappingBulk(BaseModel):
    items: List[ArticleMappingCreate]


class UnmappedArticleOut(BaseModel):
    article_code: str
    article_label: str
    occurrences: int


class BudgetPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    period_month: date
    upload_date: datetime
    items: List[BudgetItemOut] = []


# ── HeadcountFact ─────────────────────────────────────────────────────────────

class HeadcountFactCreate(BaseModel):
    project_id: UUID
    object_id: Optional[UUID] = None
    work_type: str
    fact_date: date
    count: int
    source: HeadcountSource = HeadcountSource.MANUAL
    contractor_id: Optional[UUID] = None


class HeadcountFactOut(HeadcountFactCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


# ── HeadcountPlan ─────────────────────────────────────────────────────────────

class HeadcountPlanCreate(BaseModel):
    project_id: UUID
    object_id: Optional[UUID] = None
    work_type: str
    period_month: date
    planned_count: int
    contractor_id: Optional[UUID] = None


class HeadcountPlanOut(HeadcountPlanCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


# ── Dashboard types ───────────────────────────────────────────────────────────

class WorkTypeRow(BaseModel):
    """Строка по виду работ в детализации проекта/объекта"""
    work_type: str
    bdr_amount: Decimal
    management_completion_amount: Decimal
    uv_pct: float
    net_bdr: Decimal
    norm_day: Optional[Decimal]
    required_headcount: Optional[float]
    plan_report: Optional[int] = None          # план от стройки (рапорт)
    fact_30d: float
    fact_7d: float
    coverage_pct: Optional[float]              # обеспеченность vs план по деньгам
    coverage_report_pct: Optional[float] = None  # обеспеченность vs рапорт
    trend: str  # up / down / stable / no_data
    traffic_light: str                         # светофор vs план по деньгам
    traffic_light_report: str = "grey"         # светофор vs рапорт


class ObjectDashboardItem(BaseModel):
    """Строка объекта (корпуса) в детализации проекта"""
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
    """Строка проекта в сводном дашборде"""
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
    project: ProjectOut
    period_month: Optional[date]
    # Project-level KPIs
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
    # Objects with expandable work types
    objects: List[ObjectDashboardItem] = []
    # Aggregated work types (backward compatibility)
    work_types: List[WorkTypeRow] = []


# ── WfContractor ────────────────────────────────────────────────────────────────

class ContractorBase(BaseModel):
    name: str
    inn: Optional[str] = None
    description: Optional[str] = None


class ContractorCreate(ContractorBase):
    pass


class ContractorOut(ContractorBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


# ── Forecast ──────────────────────────────────────────────────────────────────

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


# ── WfContractorHeadcount ───────────────────────────────────────────────────────

class ContractorHeadcountRow(BaseModel):
    contractor_id: Optional[UUID]
    contractor_name: str
    work_type: str
    plan: Optional[int]
    fact_30d: float
    coverage_pct: Optional[float]


# ── Challenge ─────────────────────────────────────────────────────────────────

class MobilizationPlanCreate(BaseModel):
    planned_date: date
    action: str
    headcount_delta: int
    contractor_name: str


class MobilizationPlanOut(MobilizationPlanCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    challenge_item_id: UUID


class MobilizationCheckpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    mobilization_plan_id: UUID
    check_date: date
    expected_cumulative: int
    actual_cumulative: Optional[int]
    status: str
    violation_recorded: bool
    violation_comment: Optional[str]


class ChallengeItemCreate(BaseModel):
    work_type: str
    system_baseline: int = 0
    requested_count: int
    approved_count: Optional[int] = None
    requires_mobilization_plan: bool = False


class ChallengeItemOut(ChallengeItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    challenge_id: UUID
    mobilization_plans: List[MobilizationPlanOut] = []


class ChallengeCreate(BaseModel):
    project_id: UUID
    object_id: UUID
    period_month: date
    comment: Optional[str] = None
    items: List[ChallengeItemCreate] = []


class ChallengeUpdate(BaseModel):
    status: Optional[ChallengeStatus] = None
    approved_by: Optional[str] = None
    comment: Optional[str] = None


class ChallengeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    object_id: UUID
    period_month: date
    status: str
    created_at: datetime
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    comment: Optional[str]
    items: List[ChallengeItemOut] = []


class MobilizationPlanBulkCreate(BaseModel):
    challenge_item_id: UUID
    plans: List[MobilizationPlanCreate]


# ── Violation ─────────────────────────────────────────────────────────────────

class ViolationCreate(BaseModel):
    project_id: UUID
    object_id: UUID
    work_type: str
    contractor_id: Optional[UUID] = None
    violation_date: date
    violation_type: ViolationType
    description: str
    plan_count: int = 0
    fact_count: int = 0


class ViolationUpdate(BaseModel):
    escalated: Optional[bool] = None
    escalated_to: Optional[str] = None
    resolved: Optional[bool] = None


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
    # Enriched fields (filled by API, not from ORM)
    project_name: Optional[str] = None
    object_name: Optional[str] = None
    contractor_name: Optional[str] = None

class ViolationScanResult(BaseModel):
    created: int
    violations: List[ViolationOut]


# ── Analytics ─────────────────────────────────────────────────────────────────

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
