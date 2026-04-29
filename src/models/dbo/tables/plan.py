from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor
    from src.models.dbo.tables.housing import Housing, Section, Floor
    from src.models.dbo.tables.work import WorkType


class PlanSource(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    ADJUSTED = "adjusted"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled_by_rs"


class PlanItem(IDMixin, Base):
    """Single line in a daily work plan (plan-naryad)."""

    __tablename__ = "plan_items"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    housing_id: Mapped[UUID] = mapped_column(
        ForeignKey("housings.id", name="fk_plan_items_housing_id"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("sections.id", name="fk_plan_items_section_id"),
        nullable=False,
        index=True,
    )
    floor_id: Mapped[UUID] = mapped_column(
        ForeignKey("floors.id", name="fk_plan_items_floor_id"),
        nullable=False,
        index=True,
    )
    work_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_types.id", name="fk_plan_items_work_type_id"),
        nullable=False,
        index=True,
    )
    contractor_id: Mapped[UUID] = mapped_column(
        ForeignKey("contractors.id", name="fk_plan_items_contractor_id"),
        nullable=False,
        index=True,
    )

    planned_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    rs_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    rs_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rs_confirmed_by: Mapped[Optional[str]] = mapped_column(String(255))

    source: Mapped[str] = mapped_column(String(20), default=PlanSource.AUTO)
    status: Mapped[str] = mapped_column(String(20), default=PlanStatus.DRAFT)

    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
    section: Mapped["Section"] = relationship()  # type: ignore[name-defined]
    floor: Mapped["Floor"] = relationship()  # type: ignore[name-defined]
    work_type: Mapped["WorkType"] = relationship()  # type: ignore[name-defined]
    contractor: Mapped["Contractor"] = relationship()  # type: ignore[name-defined]
    adjustments: Mapped[list["PlanAdjustment"]] = relationship(
        back_populates="plan_item",
        cascade="all, delete-orphan",
    )


class PlanAdjustment(IDMixin, Base):
    """Audit log of plan-naryad modifications made by RS."""

    __tablename__ = "plan_adjustments"

    plan_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan_items.id", name="fk_plan_adjustments_plan_item_id"),
        nullable=False,
        index=True,
    )
    original_field: Mapped[str] = mapped_column(String(50), nullable=False)
    original_value: Mapped[str] = mapped_column(String(255), nullable=False)
    new_value: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    adjusted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    adjusted_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    plan_item: Mapped["PlanItem"] = relationship(back_populates="adjustments")
