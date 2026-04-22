from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin, RaportMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor


class ProjectClass(str, Enum):
    COMFORT = "Комфорт"
    BUSINESS = "Бизнес"


class HeadcountSource(str, Enum):
    MANUAL = "manual"
    API = "api"


class ChallengeStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CheckpointStatus(str, Enum):
    PENDING = "pending"
    MET = "met"
    MISSED = "missed"


class ViolationType(str, Enum):
    MOBILIZATION_MISSED = "mobilization_missed"
    COVERAGE_CRITICAL = "coverage_critical"
    PLAN_NOT_MET = "plan_not_met"


class WfProject(IDMixin, RaportMixin, Base):
    """Workforce project (residential complex or construction site)."""

    __tablename__ = "wf_projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_class: Mapped[str] = mapped_column(String(50), nullable=False, default=ProjectClass.COMFORT)
    description: Mapped[Optional[str]] = mapped_column(String(1000))

    objects: Mapped[List["WfProjectObject"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    budget_periods: Mapped[List["WfBudgetPeriod"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    headcount_facts: Mapped[List["WfHeadcountFact"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    headcount_plans: Mapped[List["WfHeadcountPlan"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class WfProjectObject(IDMixin, RaportMixin, Base):
    """Object (building / section) within a workforce project."""

    __tablename__ = "wf_project_objects"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_projects.id", name="fk_wf_project_objects_project_id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    planned_end_date: Mapped[Optional[date]] = mapped_column(Date)
    total_budget_remaining: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))

    project: Mapped["WfProject"] = relationship(back_populates="objects")
    budget_items: Mapped[List["WfBudgetItem"]] = relationship(back_populates="project_object")
    headcount_facts: Mapped[List["WfHeadcountFact"]] = relationship(back_populates="project_object")
    headcount_plans: Mapped[List["WfHeadcountPlan"]] = relationship(back_populates="project_object")
    contractor_assignments: Mapped[List["WfContractorAssignment"]] = relationship(back_populates="project_object")


class WfWorkforceNorm(IDMixin, Base):
    """Output norm (RUB / person-day) by work type and project class."""

    __tablename__ = "wf_norms"

    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    project_class: Mapped[str] = mapped_column(String(50), nullable=False)
    median_day_bdr: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    median_month_bdr: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    q1: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    q3: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    count: Mapped[Optional[int]] = mapped_column(Integer)


class WfBudgetPeriod(IDMixin, Base):
    """Uploaded monthly budget for a project."""

    __tablename__ = "wf_budget_periods"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_projects.id", name="fk_wf_budget_periods_project_id"),
        nullable=False,
        index=True,
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    upload_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    project: Mapped["WfProject"] = relationship(back_populates="budget_periods")
    items: Mapped[List["WfBudgetItem"]] = relationship(back_populates="budget_period", cascade="all, delete-orphan")


class WfBudgetItem(IDMixin, Base):
    """Budget line (work type, BDR, UV)."""

    __tablename__ = "wf_budget_items"

    budget_period_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_budget_periods.id", name="fk_wf_budget_items_budget_period_id"),
        nullable=False,
        index=True,
    )
    object_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("wf_project_objects.id", name="fk_wf_budget_items_object_id"),
        index=True,
    )
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    detailed_article: Mapped[Optional[str]] = mapped_column(String(500))
    bdr_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    management_completion_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_wf_budget_items_contractor_id"),
        index=True,
    )
    remaining_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    planned_end_date: Mapped[Optional[date]] = mapped_column(Date)

    budget_period: Mapped["WfBudgetPeriod"] = relationship(back_populates="items")
    project_object: Mapped[Optional["WfProjectObject"]] = relationship(back_populates="budget_items")
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]


class WfHeadcountFact(IDMixin, Base):
    """Actual headcount on a site per work type per date."""

    __tablename__ = "wf_headcount_facts"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_projects.id", name="fk_wf_headcount_facts_project_id"),
        nullable=False,
        index=True,
    )
    object_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("wf_project_objects.id", name="fk_wf_headcount_facts_object_id"),
        index=True,
    )
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    fact_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=HeadcountSource.MANUAL)
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_wf_headcount_facts_contractor_id"),
        index=True,
    )

    project: Mapped["WfProject"] = relationship(back_populates="headcount_facts")
    project_object: Mapped[Optional["WfProjectObject"]] = relationship(back_populates="headcount_facts")
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]


class WfHeadcountPlan(IDMixin, Base):
    """Planned headcount from report (project, work type, month)."""

    __tablename__ = "wf_headcount_plans"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_projects.id", name="fk_wf_headcount_plans_project_id"),
        nullable=False,
        index=True,
    )
    object_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("wf_project_objects.id", name="fk_wf_headcount_plans_object_id"),
        index=True,
    )
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    planned_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_wf_headcount_plans_contractor_id"),
        index=True,
    )

    project: Mapped["WfProject"] = relationship(back_populates="headcount_plans")
    project_object: Mapped[Optional["WfProjectObject"]] = relationship(back_populates="headcount_plans")
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]


class WfContractorAssignment(IDMixin, Base):
    """Assignment of a workforce contractor to an object × work type."""

    __tablename__ = "wf_contractor_assignments"

    contractor_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_wf_contractor_assignments_contractor_id"),
        nullable=False,
        index=True,
    )
    object_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_project_objects.id", name="fk_wf_contractor_assignments_object_id"),
        nullable=False,
        index=True,
    )
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)

    contractor: Mapped["Contractor"] = relationship()  # type: ignore[name-defined]
    project_object: Mapped["WfProjectObject"] = relationship(back_populates="contractor_assignments")


class WfChallenge(IDMixin, Base):
    """Mobilization request (challenge)."""

    __tablename__ = "wf_challenges"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_projects.id", name="fk_wf_challenges_project_id"),
        nullable=False,
        index=True,
    )
    object_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_project_objects.id", name="fk_wf_challenges_object_id"),
        nullable=False,
        index=True,
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ChallengeStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    comment: Mapped[Optional[str]] = mapped_column(String(1000))

    project: Mapped["WfProject"] = relationship()
    project_object: Mapped["WfProjectObject"] = relationship()
    items: Mapped[List["WfChallengeItem"]] = relationship(back_populates="challenge", cascade="all, delete-orphan")


class WfChallengeItem(IDMixin, Base):
    """Line item in a mobilization challenge (work type)."""

    __tablename__ = "wf_challenge_items"

    challenge_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_challenges.id", name="fk_wf_challenge_items_challenge_id"),
        nullable=False,
        index=True,
    )
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    system_baseline: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_count: Mapped[Optional[int]] = mapped_column(Integer)
    requires_mobilization_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    challenge: Mapped["WfChallenge"] = relationship(back_populates="items")
    mobilization_plans: Mapped[List["WfMobilizationPlan"]] = relationship(
        back_populates="challenge_item", cascade="all, delete-orphan"
    )


class WfMobilizationPlan(IDMixin, Base):
    """Step in a mobilization plan."""

    __tablename__ = "wf_mobilization_plans"

    challenge_item_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_challenge_items.id", name="fk_wf_mobilization_plans_challenge_item_id"),
        nullable=False,
        index=True,
    )
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    headcount_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    contractor_name: Mapped[str] = mapped_column(String(255), nullable=False)

    challenge_item: Mapped["WfChallengeItem"] = relationship(back_populates="mobilization_plans")
    checkpoints: Mapped[List["WfMobilizationCheckpoint"]] = relationship(
        back_populates="mobilization_plan", cascade="all, delete-orphan"
    )


class WfMobilizationCheckpoint(IDMixin, Base):
    """Control point of a mobilization plan."""

    __tablename__ = "wf_mobilization_checkpoints"

    mobilization_plan_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_mobilization_plans.id", name="fk_wf_mobilization_checkpoints_plan_id"),
        nullable=False,
        index=True,
    )
    check_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_cumulative: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_cumulative: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CheckpointStatus.PENDING)
    violation_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    violation_comment: Mapped[Optional[str]] = mapped_column(String(1000))

    mobilization_plan: Mapped["WfMobilizationPlan"] = relationship(back_populates="checkpoints")


class WfArticleMapping(IDMixin, Base):
    """Mapping of a detailed 1C budget article to an aggregated work type."""

    __tablename__ = "wf_article_mapping"

    article_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    article_label: Mapped[str] = mapped_column(String(500), nullable=False)
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)


class WfViolation(IDMixin, Base):
    """Recorded workforce violation."""

    __tablename__ = "wf_violations"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_projects.id", name="fk_wf_violations_project_id"),
        nullable=False,
        index=True,
    )
    object_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("wf_project_objects.id", name="fk_wf_violations_object_id"),
        nullable=False,
        index=True,
    )
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_wf_violations_contractor_id"),
        index=True,
    )
    violation_date: Mapped[date] = mapped_column(Date, nullable=False)
    violation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    plan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalated_to: Mapped[Optional[str]] = mapped_column(String(255))
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    project: Mapped["WfProject"] = relationship()
    project_object: Mapped["WfProjectObject"] = relationship()
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]
