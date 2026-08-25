"""Workforce («Численность») domain.

Project and ConstructionObject used to live here under a `Wf` prefix; they moved to
`project_structure.py` because plan-naryad needs them too. The `wf_` table prefix is gone
everywhere — Raport does not use module prefixes and it had already stopped being a
reliable marker (see the Р6b decision in docs/to-be-plan.md).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor
    from src.models.dbo.tables.project_structure import ConstructionObject, Project
    from src.models.dbo.tables.work import Work


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


class HeadcountNorm(IDMixin, Base):
    """Output norm (RUB / person-day) by work and project class."""

    __tablename__ = "headcount_norms"

    work_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("works.id", name="fk_headcount_norms_work_id"),
        nullable=False,
        index=True,
    )
    project_class: Mapped[str] = mapped_column(String(50), nullable=False)
    median_day_bdr: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    median_month_bdr: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    q1: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    q3: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    count: Mapped[Optional[int]] = mapped_column(Integer)

    work: Mapped["Work"] = relationship(lazy="selectin")


class BudgetPeriod(IDMixin, Base):
    """Uploaded monthly budget for a project."""

    __tablename__ = "budget_periods"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("projects.id", name="fk_budget_periods_project_id"),
        nullable=False,
        index=True,
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    upload_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    project: Mapped["Project"] = relationship(back_populates="budget_periods")
    items: Mapped[List["BudgetItem"]] = relationship(back_populates="budget_period", cascade="all, delete-orphan")


class ArticleBDR(IDMixin, Base):
    """Master table for 1C budget articles."""

    __tablename__ = "article_bdrs"

    code_1c: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Declared explicitly because migration 6ae947202dd1 created it as a named
    # constraint; without it here `alembic check` reports permanent drift.
    __table_args__ = (UniqueConstraint("code_1c", name="uq_article_bdrs_code_1c"),)

    def __str__(self) -> str:
        return f"{self.code_1c} — {self.name}"

    works: Mapped[List["ArticleBDRWork"]] = relationship(back_populates="article_bdr", cascade="all, delete-orphan")


class ArticleBDRWork(IDMixin, Base):
    """M2M link between a 1C budget article and a work."""

    __tablename__ = "article_bdr_works"

    article_bdr_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("article_bdrs.id", name="fk_article_bdr_works_article_bdr_id"),
        nullable=False,
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("works.id", name="fk_article_bdr_works_work_id"),
        nullable=False,
        index=True,
    )

    article_bdr: Mapped["ArticleBDR"] = relationship(back_populates="works")
    work: Mapped["Work"] = relationship(lazy="selectin")


class BudgetItem(IDMixin, Base):
    """Budget line (work, BDR, UV)."""

    __tablename__ = "budget_items"

    budget_period_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("budget_periods.id", name="fk_budget_items_budget_period_id"),
        nullable=False,
        index=True,
    )
    construction_object_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("construction_objects.id", name="fk_budget_items_construction_object_id"),
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("works.id", name="fk_budget_items_work_id"),
        nullable=False,
        index=True,
    )
    article_bdr_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("article_bdrs.id", name="fk_budget_items_article_bdr_id"),
        nullable=True,
        index=True,
    )
    bdr_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    management_completion_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_budget_items_contractor_id"),
        index=True,
    )
    remaining_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    planned_end_date: Mapped[Optional[date]] = mapped_column(Date)

    budget_period: Mapped["BudgetPeriod"] = relationship(back_populates="items")
    construction_object: Mapped[Optional["ConstructionObject"]] = relationship()  # type: ignore[name-defined]
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship(lazy="selectin")
    article_bdr: Mapped[Optional["ArticleBDR"]] = relationship()


class HeadcountFact(IDMixin, Base):
    """Actual headcount on a site per work per date."""

    __tablename__ = "headcount_facts"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("projects.id", name="fk_headcount_facts_project_id"),
        nullable=False,
        index=True,
    )
    construction_object_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("construction_objects.id", name="fk_headcount_facts_construction_object_id"),
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("works.id", name="fk_headcount_facts_work_id"),
        nullable=False,
        index=True,
    )
    fact_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=HeadcountSource.MANUAL)
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_headcount_facts_contractor_id"),
        index=True,
    )

    project: Mapped["Project"] = relationship(back_populates="headcount_facts")
    construction_object: Mapped[Optional["ConstructionObject"]] = relationship()  # type: ignore[name-defined]
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship(lazy="selectin")


class HeadcountPlan(IDMixin, Base):
    """Planned headcount from report (project, work, month)."""

    __tablename__ = "headcount_plans"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("projects.id", name="fk_headcount_plans_project_id"),
        nullable=False,
        index=True,
    )
    construction_object_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("construction_objects.id", name="fk_headcount_plans_construction_object_id"),
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("works.id", name="fk_headcount_plans_work_id"),
        nullable=False,
        index=True,
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    planned_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_headcount_plans_contractor_id"),
        index=True,
    )

    project: Mapped["Project"] = relationship(back_populates="headcount_plans")
    construction_object: Mapped[Optional["ConstructionObject"]] = relationship()  # type: ignore[name-defined]
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship(lazy="selectin")


class ContractorAssignment(IDMixin, Base):
    """Workforce assignment of a contractor to a construction object × work.

    Not to be confused with Raport `contractor_works` (contractor × section × floor ×
    work) — those are read online and never stored, see Р1.
    """

    __tablename__ = "contractor_assignments"

    contractor_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_contractor_assignments_contractor_id"),
        nullable=False,
        index=True,
    )
    construction_object_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("construction_objects.id", name="fk_contractor_assignments_construction_object_id"),
        nullable=False,
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("works.id", name="fk_contractor_assignments_work_id"),
        nullable=False,
        index=True,
    )

    contractor: Mapped["Contractor"] = relationship()  # type: ignore[name-defined]
    construction_object: Mapped["ConstructionObject"] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship(lazy="selectin")


class Challenge(IDMixin, Base):
    """Mobilization request (challenge)."""

    __tablename__ = "challenges"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("projects.id", name="fk_challenges_project_id"),
        nullable=False,
        index=True,
    )
    construction_object_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("construction_objects.id", name="fk_challenges_construction_object_id"),
        nullable=False,
        index=True,
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ChallengeStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    comment: Mapped[Optional[str]] = mapped_column(String(1000))

    project: Mapped["Project"] = relationship()
    construction_object: Mapped["ConstructionObject"] = relationship()  # type: ignore[name-defined]
    items: Mapped[List["ChallengeItem"]] = relationship(back_populates="challenge", cascade="all, delete-orphan")


class ChallengeItem(IDMixin, Base):
    """Line item in a mobilization challenge (work)."""

    __tablename__ = "challenge_items"

    challenge_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("challenges.id", name="fk_challenge_items_challenge_id"),
        nullable=False,
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("works.id", name="fk_challenge_items_work_id"),
        nullable=False,
        index=True,
    )
    system_baseline: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_count: Mapped[Optional[int]] = mapped_column(Integer)
    requires_mobilization_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    challenge: Mapped["Challenge"] = relationship(back_populates="items")
    work: Mapped["Work"] = relationship(lazy="selectin")
    mobilization_plans: Mapped[List["MobilizationPlan"]] = relationship(
        back_populates="challenge_item", cascade="all, delete-orphan"
    )


class MobilizationPlan(IDMixin, Base):
    """Step in a mobilization plan."""

    __tablename__ = "mobilization_plans"

    challenge_item_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("challenge_items.id", name="fk_mobilization_plans_challenge_item_id"),
        nullable=False,
        index=True,
    )
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    headcount_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    contractor_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_mobilization_plans_contractor_id"),
        nullable=False,
        index=True,
    )

    challenge_item: Mapped["ChallengeItem"] = relationship(back_populates="mobilization_plans")
    contractor: Mapped["Contractor"] = relationship()  # type: ignore[name-defined]
    checkpoints: Mapped[List["MobilizationCheckpoint"]] = relationship(
        back_populates="mobilization_plan", cascade="all, delete-orphan"
    )


class MobilizationCheckpoint(IDMixin, Base):
    """Control point of a mobilization plan."""

    __tablename__ = "mobilization_checkpoints"

    mobilization_plan_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("mobilization_plans.id", name="fk_mobilization_checkpoints_plan_id"),
        nullable=False,
        index=True,
    )
    check_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_cumulative: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_cumulative: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CheckpointStatus.PENDING)
    violation_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    violation_comment: Mapped[Optional[str]] = mapped_column(String(1000))

    mobilization_plan: Mapped["MobilizationPlan"] = relationship(back_populates="checkpoints")


class Violation(IDMixin, Base):
    """Recorded workforce violation."""

    __tablename__ = "violations"

    project_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("projects.id", name="fk_violations_project_id"),
        nullable=False,
        index=True,
    )
    construction_object_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("construction_objects.id", name="fk_violations_construction_object_id"),
        nullable=False,
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        sa.UUID,
        ForeignKey("works.id", name="fk_violations_work_id"),
        nullable=False,
        index=True,
    )
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        sa.UUID,
        ForeignKey("contractors.id", name="fk_violations_contractor_id"),
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

    project: Mapped["Project"] = relationship()
    construction_object: Mapped["ConstructionObject"] = relationship()  # type: ignore[name-defined]
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship(lazy="selectin")
