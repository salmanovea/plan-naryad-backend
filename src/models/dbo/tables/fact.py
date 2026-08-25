from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin, RaportMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor
    from src.models.dbo.tables.housing import Housing, Section, Floor
    from src.models.dbo.tables.work import Work


class FactSource(str, Enum):
    """Where the row came from. Everything real is `RAPORT` now — the spec forbids creating
    facts in plan-naryad, they are only mirrored in."""

    RAPORT = "raport"
    CONTRACTOR_BOT = "contractor_bot"
    CONTRACTOR_WEB = "contractor_web"
    RS_WEB = "rs_web"


class WorkFact(IDMixin, RaportMixin, Base):
    """A work completion fact, mirrored from Raport.

    Facts are entered in Raport only (spec: «создание новых фактов в План-наряде не
    предусмотрено»); `raport_id` holds the Raport `work_fact.id` and is the upsert key.
    """

    __tablename__ = "work_facts"

    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
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
    work_id: Mapped[UUID] = mapped_column(
        ForeignKey("works.id", name="fk_work_facts_work_id"),
        nullable=False,
        index=True,
    )
    # Nullable on purpose. Raport leaves `contractor` and `work_cell_contractor_id` empty on
    # essentially every fact (0 of 56 365 on the reference housing), so the contractor is
    # derived from the cell's assignment. That works for 99.5% of cells; the rest have more
    # than one contractor and cannot be attributed — but the fact still happened and must be
    # stored, otherwise reconciliation loses «факт без плана» rows.
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("contractors.id", name="fk_work_facts_contractor_id"),
        index=True,
    )

    # Facts come from Raport, where they are entered as a percent — `volume` is 0 on the
    # overwhelming majority of rows. Kept in the DB but not exposed (Р6).
    volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    unit: Mapped[Optional[str]] = mapped_column(String(20))

    # Raport identifiers — `work_cell_contractor_id` is the grain of execution (Р0).
    work_cell_contractor_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), index=True)
    work_cell_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), index=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    submitted_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default=FactSource.CONTRACTOR_WEB)

    comment: Mapped[Optional[str]] = mapped_column(Text)
    photo_urls: Mapped[Optional[str]] = mapped_column(Text)

    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
    section: Mapped["Section"] = relationship()  # type: ignore[name-defined]
    floor: Mapped["Floor"] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship()  # type: ignore[name-defined]
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]
