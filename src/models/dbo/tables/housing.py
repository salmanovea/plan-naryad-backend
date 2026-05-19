from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin, RaportMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.workforce import WfProjectObject


class Housing(IDMixin, RaportMixin, Base):
    """Building (corpus) within a residential complex."""

    __tablename__ = "housings"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    complex_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    construction_object_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wf_project_objects.id", name="fk_housings_construction_object_id"),
        nullable=True,
        index=True,
    )

    def __str__(self) -> str:
        return self.name

    construction_object: Mapped[Optional["WfProjectObject"]] = relationship(foreign_keys=[construction_object_id])  # type: ignore[name-defined]
    sections: Mapped[List["Section"]] = relationship(back_populates="housing", cascade="all, delete-orphan")


class Section(IDMixin, RaportMixin, Base):
    """Section within a building."""

    __tablename__ = "sections"

    housing_id: Mapped[UUID] = mapped_column(
        ForeignKey("housings.id", name="fk_sections_housing_id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    section_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))

    def __str__(self) -> str:
        return self.name

    housing: Mapped["Housing"] = relationship(back_populates="sections")
    floors: Mapped[List["Floor"]] = relationship(back_populates="section", cascade="all, delete-orphan")


class Floor(IDMixin, RaportMixin, Base):
    """Floor within a section."""

    __tablename__ = "floors"

    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("sections.id", name="fk_floors_section_id"),
        nullable=False,
        index=True,
    )
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(500))

    def __str__(self) -> str:
        return self.name or str(self.floor_number)

    section: Mapped["Section"] = relationship(back_populates="floors")
