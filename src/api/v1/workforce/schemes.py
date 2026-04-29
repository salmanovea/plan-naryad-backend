from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import IDMixinSchema, NamedEntitySchema
from src.models.dbo.tables.workforce import ChallengeStatus, HeadcountSource, ProjectClass, ViolationType

# Re-export dashboard DTOs from service layer
from src.services.workforce.schemas import (  # noqa: F401
    ContractorHeadcountRow,
    ContractorRatingRow,
    DashboardResponse,
    ForecastResponse,
    ForecastRow,
    ObjectDashboardItem,
    ProjectDetailResponse,
    ProjectRow,
    SystemProblemRow,
    SystemProblemsResponse,
    ViolationOut,
    ViolationScanResult,
    WfProjectOut,
    WorkTypeRow,
)


# ── WfProject ─────────────────────────────────────────────────────────────────


class CreateWfProjectRequest(BaseModel):
    name: str
    project_class: ProjectClass = ProjectClass.COMFORT
    description: Optional[str] = None


class UpdateWfProjectRequest(BaseModel):
    name: Optional[str] = None
    project_class: Optional[ProjectClass] = None
    description: Optional[str] = None


# ── WfProjectObject ───────────────────────────────────────────────────────────


class CreateWfProjectObjectRequest(BaseModel):
    name: str
    description: Optional[str] = None
    planned_end_date: Optional[date] = None


class WfProjectObjectSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    name: str
    description: Optional[str] = None
    planned_end_date: Optional[date] = None
    total_budget_remaining: Optional[Decimal] = None


# ── WorkforceNorm ─────────────────────────────────────────────────────────────


class CreateWfWorkforceNormRequest(BaseModel):
    work_type_id: UUID
    project_class: ProjectClass
    median_day_bdr: Decimal
    median_month_bdr: Decimal
    q1: Optional[Decimal] = None
    q3: Optional[Decimal] = None
    count: Optional[int] = None


class WfWorkforceNormSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    work_type: NamedEntitySchema
    project_class: str
    median_day_bdr: Decimal
    median_month_bdr: Decimal
    q1: Optional[Decimal] = None
    q3: Optional[Decimal] = None
    count: Optional[int] = None


# ── HeadcountFact ─────────────────────────────────────────────────────────────


class CreateWfHeadcountFactRequest(BaseModel):
    project_id: UUID
    object_id: Optional[UUID] = None
    work_type_id: UUID
    fact_date: date
    count: int
    source: HeadcountSource = HeadcountSource.MANUAL
    contractor_id: Optional[UUID] = None


class WfHeadcountFactSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    object_id: Optional[UUID] = None
    work_type: NamedEntitySchema
    fact_date: date
    count: int
    source: str
    contractor_id: Optional[UUID] = None


# ── HeadcountPlan ─────────────────────────────────────────────────────────────


class CreateWfHeadcountPlanRequest(BaseModel):
    project_id: UUID
    object_id: Optional[UUID] = None
    work_type_id: UUID
    period_month: date
    planned_count: int
    contractor_id: Optional[UUID] = None


class WfHeadcountPlanSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    object_id: Optional[UUID] = None
    work_type: NamedEntitySchema
    period_month: date
    planned_count: int
    contractor_id: Optional[UUID] = None


# ── Challenge ─────────────────────────────────────────────────────────────────


class CreateChallengeItemRequest(BaseModel):
    work_type_id: UUID
    system_baseline: int = 0
    requested_count: int
    approved_count: Optional[int] = None
    requires_mobilization_plan: bool = False


class CreateChallengeRequest(BaseModel):
    project_id: UUID
    object_id: UUID
    period_month: date
    comment: Optional[str] = None
    items: List[CreateChallengeItemRequest] = []


class UpdateChallengeRequest(BaseModel):
    status: Optional[ChallengeStatus] = None
    approved_by: Optional[str] = None
    comment: Optional[str] = None


class ChallengeItemSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    challenge_id: UUID
    work_type: NamedEntitySchema
    system_baseline: int
    requested_count: int
    approved_count: Optional[int] = None
    requires_mobilization_plan: bool


class ChallengeSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    object_id: UUID
    period_month: date
    status: str
    approved_by: Optional[str] = None
    comment: Optional[str] = None
    items: List[ChallengeItemSchema] = []


# ── Violation ─────────────────────────────────────────────────────────────────


class CreateViolationRequest(BaseModel):
    project_id: UUID
    object_id: UUID
    work_type_id: UUID
    contractor_id: Optional[UUID] = None
    violation_date: date
    violation_type: ViolationType
    description: str
    plan_count: int = 0
    fact_count: int = 0


class UpdateViolationRequest(BaseModel):
    escalated: Optional[bool] = None
    escalated_to: Optional[str] = None
    resolved: Optional[bool] = None


# ── ArticleMapping ────────────────────────────────────────────────────────────


class CreateArticleMappingRequest(BaseModel):
    article_code: str
    article_label: str
    work_type_id: UUID


class ArticleMappingSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    article_code: str
    article_label: str
    work_type: NamedEntitySchema


class ArticleMappingBulkRequest(BaseModel):
    items: List[CreateArticleMappingRequest]


class UnmappedArticleSchema(BaseModel):
    article_code: str
    article_label: str
    occurrences: int


# ── Filters ───────────────────────────────────────────────────────────────────


class WfProjectFilters(BaseModel):
    search: Optional[str] = Query(None, description="Search in project name")
    project_class: Optional[ProjectClass] = Query(None, description="Filter by project class")


class WfViolationFilters(BaseModel):
    project_id: Optional[UUID] = Query(None)
    object_id: Optional[UUID] = Query(None)
    resolved: Optional[bool] = Query(None)
    escalated: Optional[bool] = Query(None)
