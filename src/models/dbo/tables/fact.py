from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor
    from src.models.dbo.tables.housing import Housing, Section, Floor
    from src.models.dbo.tables.work import WorkType


class FactSource(str, Enum):
    CONTRACTOR_BOT = "contractor_bot"
    CONTRACTOR_WEB = "contractor_web"
    RS_WEB = "rs_web"


class WorkFact(IDMixin, Base):
    """Actual work completion report submitted by a contractor."""

    __tablename__ = "work_facts"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    housing_id: Mapped[UUID] = mapped_column(
        ForeignKey("housings.id", name="fk_work_facts_housing_id"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("sections.id", name="fk_work_facts_section_id"),
        nullable=False,
        index=True,
    )
    floor_id: Mapped[UUID] = mapped_column(
        ForeignKey("floors.id", name="fk_work_facts_floor_id"),
        nullable=False,
        index=True,
    )
    work_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_types.id", name="fk_work_facts_work_type_id"),
        nullable=False,
        index=True,
    )
    contractor_id: Mapped[UUID] = mapped_column(
        ForeignKey("contractors.id", name="fk_work_facts_contractor_id"),
        nullable=False,
        index=True,
    )

    actual_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    submitted_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default=FactSource.CONTRACTOR_WEB)

    comment: Mapped[Optional[str]] = mapped_column(Text)
    photo_urls: Mapped[Optional[str]] = mapped_column(Text)

    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
    section: Mapped["Section"] = relationship()  # type: ignore[name-defined]
    floor: Mapped["Floor"] = relationship()  # type: ignore[name-defined]
    work_type: Mapped["WorkType"] = relationship()  # type: ignore[name-defined]
    contractor: Mapped["Contractor"] = relationship()  # type: ignore[name-defined]
