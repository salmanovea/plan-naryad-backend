"""Project structure mirrored from Raport: project → queue → construction object → housing.

Housing, Section and Floor continue to live in `housing.py`; this module holds the three
levels above them. The chain matches Raport one-to-one so synchronisation stays simple.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin, RaportMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.housing import Housing
    from src.models.dbo.tables.workforce import BudgetPeriod, HeadcountFact, HeadcountPlan


class ProjectClass(str, Enum):
    COMFORT = "Комфорт"
    BUSINESS = "Бизнес"


class Project(IDMixin, RaportMixin, Base):
    """Top of the structure. Mirrors Raport `project`."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_class: Mapped[str] = mapped_column(String(50), nullable=False, default=ProjectClass.COMFORT)
    description: Mapped[Optional[str]] = mapped_column(String(1000))

    def __str__(self) -> str:
        return self.name

    queues: Mapped[List["Queue"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    construction_objects: Mapped[List["ConstructionObject"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    budget_periods: Mapped[List["BudgetPeriod"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    headcount_facts: Mapped[List["HeadcountFact"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    headcount_plans: Mapped[List["HeadcountPlan"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Queue(IDMixin, RaportMixin, Base):
    """Construction queue («очередь») inside a project. Mirrors Raport `queue`."""

    __tablename__ = "queues"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", name="fk_queues_project_id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)

    def __str__(self) -> str:
        return self.name

    project: Mapped["Project"] = relationship(back_populates="queues")
    construction_objects: Mapped[List["ConstructionObject"]] = relationship(back_populates="queue")


class ConstructionObject(IDMixin, RaportMixin, Base):
    """Construction object («объект строительства»). Mirrors Raport `construction_object`."""

    __tablename__ = "construction_objects"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", name="fk_construction_objects_project_id"),
        nullable=False,
        index=True,
    )
    queue_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("queues.id", name="fk_construction_objects_queue_id"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    planned_end_date: Mapped[Optional[date]] = mapped_column(Date)
    total_budget_remaining: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))

    def __str__(self) -> str:
        return self.name

    project: Mapped["Project"] = relationship(back_populates="construction_objects")
    queue: Mapped[Optional["Queue"]] = relationship(back_populates="construction_objects")
    housings: Mapped[List["Housing"]] = relationship(back_populates="construction_object")  # type: ignore[name-defined]
