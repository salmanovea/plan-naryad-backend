"""
Модели для модуля управления численностью (Workforce Management).
"""
from decimal import Decimal
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import String, Integer, Numeric, ForeignKey, Date, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


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


class Project(Base):
    """Проект (жилой комплекс/объект строительства)"""
    __tablename__ = "wf_projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_class: Mapped[str] = mapped_column(String(50), nullable=False, default=ProjectClass.COMFORT)
    description: Mapped[Optional[str]] = mapped_column(String(1000))

    # Связи
    objects: Mapped[List["ProjectObject"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    budget_periods: Mapped[List["BudgetPeriod"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    headcount_facts: Mapped[List["HeadcountFact"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    headcount_plans: Mapped[List["HeadcountPlan"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectObject(Base):
    """Объект внутри проекта (корпус/секция)"""
    __tablename__ = "wf_project_objects"

    project_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    planned_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    total_budget_remaining: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2), nullable=True)

    # Связи
    project: Mapped["Project"] = relationship(back_populates="objects")
    budget_items: Mapped[List["BudgetItem"]] = relationship(back_populates="project_object")
    headcount_facts: Mapped[List["HeadcountFact"]] = relationship(back_populates="project_object")
    headcount_plans: Mapped[List["HeadcountPlan"]] = relationship(back_populates="project_object")
    contractor_assignments: Mapped[List["WfContractorAssignment"]] = relationship(back_populates="project_object")


class WorkforceNorm(Base):
    """Норматив выработки (руб./чел.день) по виду работ и классу проекта"""
    __tablename__ = "wf_norms"

    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    project_class: Mapped[str] = mapped_column(String(50), nullable=False)
    median_day_bdr: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    median_month_bdr: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    q1: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    q3: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    count: Mapped[Optional[int]] = mapped_column(Integer)


class BudgetPeriod(Base):
    """Загруженный бюджет на период (месяц)"""
    __tablename__ = "wf_budget_periods"

    project_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_projects.id"), nullable=False)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)  # первое число месяца
    upload_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Связи
    project: Mapped["Project"] = relationship(back_populates="budget_periods")
    items: Mapped[List["BudgetItem"]] = relationship(back_populates="budget_period", cascade="all, delete-orphan")


class BudgetItem(Base):
    """Строка бюджета (вид работ, БДР, УВ)"""
    __tablename__ = "wf_budget_items"

    budget_period_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_budget_periods.id"), nullable=False)
    object_id: Mapped[Optional[sa.UUID]] = mapped_column(sa.UUID, ForeignKey("wf_project_objects.id"), nullable=True)
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    detailed_article: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bdr_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    management_completion_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    contractor_id: Mapped[Optional[sa.UUID]] = mapped_column(sa.UUID, ForeignKey("wf_contractors.id"), nullable=True)
    remaining_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2), nullable=True)
    planned_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Связи
    budget_period: Mapped["BudgetPeriod"] = relationship(back_populates="items")
    project_object: Mapped[Optional["ProjectObject"]] = relationship(back_populates="budget_items")
    contractor: Mapped[Optional["WfContractor"]] = relationship(back_populates="budget_items")


class HeadcountFact(Base):
    """Факт численности на объекте по виду работ за дату"""
    __tablename__ = "wf_headcount_facts"

    project_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_projects.id"), nullable=False)
    object_id: Mapped[Optional[sa.UUID]] = mapped_column(sa.UUID, ForeignKey("wf_project_objects.id"), nullable=True)
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    fact_date: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=HeadcountSource.MANUAL)
    contractor_id: Mapped[Optional[sa.UUID]] = mapped_column(sa.UUID, ForeignKey("wf_contractors.id"), nullable=True)

    # Связи
    project: Mapped["Project"] = relationship(back_populates="headcount_facts")
    project_object: Mapped[Optional["ProjectObject"]] = relationship(back_populates="headcount_facts")
    contractor: Mapped[Optional["WfContractor"]] = relationship(back_populates="headcount_facts")


class HeadcountPlan(Base):
    """Плановая численность по рапорту (проект, вид работ, месяц)"""
    __tablename__ = "wf_headcount_plans"

    project_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_projects.id"), nullable=False)
    object_id: Mapped[Optional[sa.UUID]] = mapped_column(sa.UUID, ForeignKey("wf_project_objects.id"), nullable=True)
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)  # первое число месяца
    planned_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contractor_id: Mapped[Optional[sa.UUID]] = mapped_column(sa.UUID, ForeignKey("wf_contractors.id"), nullable=True)

    # Связи
    project: Mapped["Project"] = relationship(back_populates="headcount_plans")
    project_object: Mapped[Optional["ProjectObject"]] = relationship(back_populates="headcount_plans")
    contractor: Mapped[Optional["WfContractor"]] = relationship(back_populates="headcount_plans")


# ── Contractor ────────────────────────────────────────────────────────────────

class WfContractor(Base):
    """Подрядчик"""
    __tablename__ = "wf_contractors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Связи
    assignments: Mapped[List["WfContractorAssignment"]] = relationship(back_populates="contractor", cascade="all, delete-orphan")
    headcount_facts: Mapped[List["HeadcountFact"]] = relationship(back_populates="contractor")
    headcount_plans: Mapped[List["HeadcountPlan"]] = relationship(back_populates="contractor")
    budget_items: Mapped[List["BudgetItem"]] = relationship(back_populates="contractor")
    violations: Mapped[List["Violation"]] = relationship(back_populates="contractor")


class WfContractorAssignment(Base):
    """Назначение подрядчика на объект × вид работ"""
    __tablename__ = "wf_contractor_assignments"

    contractor_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_contractors.id"), nullable=False)
    object_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_project_objects.id"), nullable=False)
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)

    # Связи
    contractor: Mapped["WfContractor"] = relationship(back_populates="assignments")
    project_object: Mapped["ProjectObject"] = relationship(back_populates="contractor_assignments")


# ── Challenge ─────────────────────────────────────────────────────────────────

class Challenge(Base):
    """Заявка на мобилизацию (челлендж)"""
    __tablename__ = "wf_challenges"

    project_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_projects.id"), nullable=False)
    object_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_project_objects.id"), nullable=False)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ChallengeStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Связи
    project: Mapped["Project"] = relationship()
    project_object: Mapped["ProjectObject"] = relationship()
    items: Mapped[List["ChallengeItem"]] = relationship(back_populates="challenge", cascade="all, delete-orphan")


class ChallengeItem(Base):
    """Строка заявки (вид работ)"""
    __tablename__ = "wf_challenge_items"

    challenge_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_challenges.id"), nullable=False)
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    system_baseline: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requires_mobilization_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Связи
    challenge: Mapped["Challenge"] = relationship(back_populates="items")
    mobilization_plans: Mapped[List["MobilizationPlan"]] = relationship(back_populates="challenge_item", cascade="all, delete-orphan")


class MobilizationPlan(Base):
    """Шаг плана мобилизации"""
    __tablename__ = "wf_mobilization_plans"

    challenge_item_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_challenge_items.id"), nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    headcount_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    contractor_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Связи
    challenge_item: Mapped["ChallengeItem"] = relationship(back_populates="mobilization_plans")
    checkpoints: Mapped[List["MobilizationCheckpoint"]] = relationship(back_populates="mobilization_plan", cascade="all, delete-orphan")


class MobilizationCheckpoint(Base):
    """Контрольная точка плана мобилизации"""
    __tablename__ = "wf_mobilization_checkpoints"

    mobilization_plan_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_mobilization_plans.id"), nullable=False)
    check_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_cumulative: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_cumulative: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CheckpointStatus.PENDING)
    violation_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    violation_comment: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Связи
    mobilization_plan: Mapped["MobilizationPlan"] = relationship(back_populates="checkpoints")


# ── Article Mapping ───────────────────────────────────────────────────────────

class ArticleMapping(Base):
    """Маппинг детальной статьи бюджета (из 1С) на укрупнённый вид работ (норматив)."""
    __tablename__ = "wf_article_mapping"

    article_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    article_label: Mapped[str] = mapped_column(String(500), nullable=False)
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)


# ── Violation ─────────────────────────────────────────────────────────────────

class Violation(Base):
    """Зафиксированное нарушение"""
    __tablename__ = "wf_violations"

    project_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_projects.id"), nullable=False)
    object_id: Mapped[sa.UUID] = mapped_column(sa.UUID, ForeignKey("wf_project_objects.id"), nullable=False)
    work_type: Mapped[str] = mapped_column(String(255), nullable=False)
    contractor_id: Mapped[Optional[sa.UUID]] = mapped_column(sa.UUID, ForeignKey("wf_contractors.id"), nullable=True)
    violation_date: Mapped[date] = mapped_column(Date, nullable=False)
    violation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    plan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalated_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Связи
    project: Mapped["Project"] = relationship()
    project_object: Mapped["ProjectObject"] = relationship()
    contractor: Mapped[Optional["WfContractor"]] = relationship(back_populates="violations")
