from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor
    from src.models.dbo.tables.housing import Housing, Section, Floor
    from src.models.dbo.tables.work import WorkType
    from src.models.dbo.tables.plan import PlanItem
    from src.models.dbo.tables.fact import WorkFact


class ReconciliationStatus(str, Enum):
    DONE_FULL = "DONE_FULL"
    DONE_PARTIAL = "DONE_PARTIAL"
    DONE_OVER = "DONE_OVER"
    NOT_DONE = "NOT_DONE"
    NO_REPORT = "NO_REPORT"
    UNPLANNED = "UNPLANNED"


class ReconciliationPattern(str, Enum):
    WRONG_LOCATION = "WRONG_LOCATION"
    WRONG_WORK_TYPE = "WRONG_WORK_TYPE"
    CHRONIC_NO_REPORT = "CHRONIC_NO_REPORT"
    CHRONIC_UNDERPERFORM = "CHRONIC_UNDERPERFORM"


class ReconciliationResult(IDMixin, Base):
    """Plan vs. fact reconciliation result for a single work line."""

    __tablename__ = "reconciliation_results"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    housing_id: Mapped[UUID] = mapped_column(
        ForeignKey("housings.id", name="fk_reconciliation_results_housing_id"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("sections.id", name="fk_reconciliation_results_section_id"),
        nullable=False,
        index=True,
    )
    floor_id: Mapped[UUID] = mapped_column(
        ForeignKey("floors.id", name="fk_reconciliation_results_floor_id"),
        nullable=False,
        index=True,
    )
    work_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_types.id", name="fk_reconciliation_results_work_type_id"),
        nullable=False,
        index=True,
    )
    contractor_id: Mapped[UUID] = mapped_column(
        ForeignKey("contractors.id", name="fk_reconciliation_results_contractor_id"),
        nullable=False,
        index=True,
    )

    planned_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    actual_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    completion_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    pattern: Mapped[Optional[str]] = mapped_column(String(30))

    plan_item_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("plan_items.id", name="fk_reconciliation_results_plan_item_id"),
        index=True,
    )
    work_fact_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("work_facts.id", name="fk_reconciliation_results_work_fact_id"),
        index=True,
    )

    fact_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    fact_is_late: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
    section: Mapped["Section"] = relationship()  # type: ignore[name-defined]
    floor: Mapped["Floor"] = relationship()  # type: ignore[name-defined]
    work_type: Mapped["WorkType"] = relationship()  # type: ignore[name-defined]
    contractor: Mapped["Contractor"] = relationship()  # type: ignore[name-defined]
    plan_item: Mapped[Optional["PlanItem"]] = relationship()  # type: ignore[name-defined]
    work_fact: Mapped[Optional["WorkFact"]] = relationship()  # type: ignore[name-defined]


class DailySummary(IDMixin, Base):
    """Daily aggregated metrics for a building."""

    __tablename__ = "daily_summaries"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    housing_id: Mapped[UUID] = mapped_column(
        ForeignKey("housings.id", name="fk_daily_summaries_housing_id"),
        nullable=False,
        index=True,
    )

    total_planned: Mapped[int] = mapped_column(Integer, default=0)
    total_done_full: Mapped[int] = mapped_column(Integer, default=0)
    total_done_partial: Mapped[int] = mapped_column(Integer, default=0)
    total_done_over: Mapped[int] = mapped_column(Integer, default=0)
    total_not_done: Mapped[int] = mapped_column(Integer, default=0)
    total_no_report: Mapped[int] = mapped_column(Integer, default=0)
    total_unplanned: Mapped[int] = mapped_column(Integer, default=0)

    # Stored as a 0..1 fraction (same scale as ReconciliationResult.completion_ratio),
    # not a 0..100 percentage. Numeric(6, 4) keeps sub-percent precision.
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    weighted_completion: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    submission_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)

    contractor_details: Mapped[Optional[Any]] = mapped_column(JSON)
    alerts: Mapped[Optional[Any]] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
