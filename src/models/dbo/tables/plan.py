from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor
    from src.models.dbo.tables.housing import Housing, Section, Floor
    from src.models.dbo.tables.work import Work


class PlanSource(str, Enum):
    """How a plan item came to be. `ADJUSTED` is retired — editing is delete + re-add."""

    AUTO = "auto"
    MANUAL = "manual"
    ADJUSTED = "adjusted"


class PlanStatus(str, Enum):
    """`CANCELLED` is retired — items are deleted outright."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    TRANSFERRED = "transferred"
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
    work_id: Mapped[UUID] = mapped_column(
        ForeignKey("works.id", name="fk_plan_items_work_id"),
        nullable=False,
        index=True,
    )
    contractor_id: Mapped[UUID] = mapped_column(
        ForeignKey("contractors.id", name="fk_plan_items_contractor_id"),
        nullable=False,
        index=True,
    )

    # Percent of the cell held by this contractor at the moment the plan was generated —
    # the «% Исходный» column in reconciliation. Read from work_cell_contractor.percent.
    source_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))

    # Raport identifiers. `work_cell_contractor_id` is the grain of execution (Р0) and the
    # key Raport uses to light up cells in the «Задание на день» view.
    work_cell_contractor_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), index=True)
    work_cell_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), index=True)

    # Volumes are on their way out — no one sets a daily norm any more. Nullable now,
    # dropped once the frontend stops reading them.
    planned_volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    unit: Mapped[Optional[str]] = mapped_column(String(20))

    rs_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    rs_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rs_confirmed_by: Mapped[Optional[str]] = mapped_column(String(255))

    source: Mapped[str] = mapped_column(String(20), default=PlanSource.AUTO)
    status: Mapped[str] = mapped_column(String(20), default=PlanStatus.DRAFT)

    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
    section: Mapped["Section"] = relationship()  # type: ignore[name-defined]
    floor: Mapped["Floor"] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship()  # type: ignore[name-defined]
    contractor: Mapped["Contractor"] = relationship()  # type: ignore[name-defined]
