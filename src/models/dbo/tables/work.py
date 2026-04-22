from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID

from sqlalchemy import ARRAY, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin
from src.models.dbo.base_model import Base


class DependencyType(str, Enum):
    FINISH_TO_START = "finish_to_start"
    START_TO_START = "start_to_start"


class WorkGroup(IDMixin, Base):
    """Work category (SMR, finishing, engineering, etc.)."""

    __tablename__ = "work_groups"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    order: Mapped[int] = mapped_column(Integer, default=0)

    work_types: Mapped[List["WorkType"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class WorkType(IDMixin, Base):
    """Specific work type within a group."""

    __tablename__ = "work_types"

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_groups.id", name="fk_work_types_group_id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000))

    group: Mapped["WorkGroup"] = relationship(back_populates="work_types")
    tech_sequence_items: Mapped[List["TechSequenceItem"]] = relationship(back_populates="work_type")


class TechSequenceItem(IDMixin, Base):
    """Technological sequence entry for a specific building."""

    __tablename__ = "tech_sequence_items"

    housing_id: Mapped[UUID] = mapped_column(
        ForeignKey("housings.id", name="fk_tech_sequence_items_housing_id"),
        nullable=False,
        index=True,
    )
    work_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_types.id", name="fk_tech_sequence_items_work_type_id"),
        nullable=False,
        index=True,
    )

    order: Mapped[int] = mapped_column(Integer, nullable=False)
    depends_on: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    dependency_type: Mapped[str] = mapped_column(String(20), default=DependencyType.FINISH_TO_START)
    lag_days: Mapped[int] = mapped_column(Integer, default=0)

    estimated_days: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_norm_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    total_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    housing: Mapped["Housing"] = relationship()  # type: ignore[name-defined]
    work_type: Mapped["WorkType"] = relationship(back_populates="tech_sequence_items")
