from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import ARRAY, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin, RaportMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.housing import Housing, Section


class DependencyType(str, Enum):
    """Raport link types, delivered over the API as dhtmlx codes.

    Only FS and SS occur in real data (132k against 11k). FF and SF are accepted and
    treated as FS — the most conservative reading — rather than silently dropped.
    """

    FINISH_TO_START = "finish_to_start"
    START_TO_START = "start_to_start"

    @classmethod
    def from_dhtmlx(cls, code: object) -> "DependencyType":
        """Map a dhtmlx link code ("0".."3") onto a dependency type."""
        return cls.START_TO_START if str(code) == "1" else cls.FINISH_TO_START


class PlanningType(str, Enum):
    """Level a work is planned down to. Mirrors Raport `PlanningType`."""

    FLOOR = "FLOOR"
    SECTION = "SECTION"
    HOUSING = "HOUSING"


class FloorSortingDirection(str, Enum):
    """Direction the work travels through floors. Mirrors Raport `FloorSortingDirection`."""

    ASC = "ASC"
    DESC = "DESC"


class WorkSet(IDMixin, RaportMixin, Base):
    """Top level of the work catalogue — «Этап». Mirrors Raport `work_set`."""

    __tablename__ = "work_sets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    order: Mapped[int] = mapped_column(Integer, default=0)

    def __str__(self) -> str:
        return self.name

    work_groups: Mapped[List["WorkGroup"]] = relationship(back_populates="work_set")


class WorkGroup(IDMixin, RaportMixin, Base):
    """Second level of the work catalogue — «Комплекс». Mirrors Raport `work_group`."""

    __tablename__ = "work_groups"

    work_set_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("work_sets.id", name="fk_work_groups_work_set_id"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    order: Mapped[int] = mapped_column(Integer, default=0)

    def __str__(self) -> str:
        return self.name

    work_set: Mapped[Optional["WorkSet"]] = relationship(back_populates="work_groups")
    work_types: Mapped[List["WorkType"]] = relationship(back_populates="work_group")


class WorkType(IDMixin, RaportMixin, Base):
    """Third level of the work catalogue — «Вид работ». Mirrors Raport `work_type`."""

    __tablename__ = "work_types"

    work_group_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("work_groups.id", name="fk_work_types_work_group_id"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    order: Mapped[int] = mapped_column(Integer, default=0)

    def __str__(self) -> str:
        return self.name

    work_group: Mapped[Optional["WorkGroup"]] = relationship(back_populates="work_types")
    works: Mapped[List["Work"]] = relationship(back_populates="work_type", cascade="all, delete-orphan")


class Work(IDMixin, RaportMixin, Base):
    """Leaf of the work catalogue — «Работа». Mirrors Raport `work`.

    Everything operational (plan items, facts, tech sequence) points here.
    """

    __tablename__ = "works"

    work_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_types.id", name="fk_works_work_type_id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000))

    def __str__(self) -> str:
        return self.name

    work_type: Mapped["WorkType"] = relationship(back_populates="works")
    tech_sequence_items: Mapped[List["TechSequenceItem"]] = relationship(back_populates="work")


class TechSequenceItem(IDMixin, Base):
    """One node of a housing's (or section's) technological sequence.

    The sequence is a **directed graph, not a chain**: a finished work can unlock several
    successors, and a work can require several predecessors to be finished first. Real data
    has up to 63 predecessors on a single node and 190 roots.

    Raport builds calendar plans at two scopes — per housing and per housing+section. A
    section-scoped row (`section_id` set) overrides the housing-wide row for that section.
    """

    __tablename__ = "tech_sequence_items"

    housing_id: Mapped[UUID] = mapped_column(
        ForeignKey("housings.id", name="fk_tech_sequence_items_housing_id"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("sections.id", name="fk_tech_sequence_items_section_id"),
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        ForeignKey("works.id", name="fk_tech_sequence_items_work_id"),
        nullable=False,
        index=True,
    )

    order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Predecessors are split by link type because they gate differently:
    #   finish-to-start — the predecessor must be finished (100%);
    #   start-to-start  — the predecessor only has to have started (> 0%).
    # A single `dependency_type` column could not describe a node that mixes both, and
    # Raport data does mix them (132k FS edges against 11k SS).
    depends_on: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    depends_on_ss: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    lag_days: Mapped[int] = mapped_column(Integer, default=0)

    # Mirrored from the Raport plan template (PlanWork): they drive how the work
    # travels through floors during plan generation.
    planning_type: Mapped[Optional[str]] = mapped_column(String(20))
    floor_sorting_direction: Mapped[Optional[str]] = mapped_column(String(4))
    lag_between_floors: Mapped[Optional[int]] = mapped_column(Integer)

    estimated_days: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_norm_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    total_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)

    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
    section: Mapped[Optional["Section"]] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship(back_populates="tech_sequence_items")

    __table_args__ = (
        Index(
            "uq_tech_sequence_items_key",
            "housing_id",
            "section_id",
            "work_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )
