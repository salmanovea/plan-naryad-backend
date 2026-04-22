from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import ARRAY, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin, RaportMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.housing import Housing, Section
    from src.models.dbo.tables.work import WorkGroup


class Contractor(IDMixin, RaportMixin, Base):
    """Contractor company."""

    __tablename__ = "contractors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    inn: Mapped[Optional[str]] = mapped_column(String(20))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(1000))

    assignments: Mapped[List["ContractorAssignment"]] = relationship(
        back_populates="contractor",
        cascade="all, delete-orphan",
    )


class ContractorAssignment(IDMixin, Base):
    """Assignment of a contractor to work types on a building."""

    __tablename__ = "contractor_assignments"

    contractor_id: Mapped[UUID] = mapped_column(
        ForeignKey("contractors.id", name="fk_contractor_assignments_contractor_id"),
        nullable=False,
        index=True,
    )
    housing_id: Mapped[UUID] = mapped_column(
        ForeignKey("housings.id", name="fk_contractor_assignments_housing_id"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("sections.id", name="fk_contractor_assignments_section_id"),
        index=True,
    )
    work_group_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("work_groups.id", name="fk_contractor_assignments_work_group_id"),
        index=True,
    )
    work_type_ids: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)

    contractor: Mapped["Contractor"] = relationship(back_populates="assignments")
    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
    section: Mapped[Optional["Section"]] = relationship()  # type: ignore[name-defined]
    work_group: Mapped[Optional["WorkGroup"]] = relationship()  # type: ignore[name-defined]
