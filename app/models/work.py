from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List, Optional
from enum import Enum

from ..database import Base


class DependencyType(str, Enum):
    FINISH_TO_START = "finish_to_start"
    START_TO_START = "start_to_start"


class WorkGroup(Base):
    """Группа работ (СМР, Отделка, Инженерка и т.д.)"""
    __tablename__ = "work_groups"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    order: Mapped[int] = mapped_column(Integer, default=0)  # Порядок группы в общей последовательности
    
    # Связи
    work_types: Mapped[List["WorkType"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class WorkType(Base):
    """Вид работ"""
    __tablename__ = "work_types"
    
    group_id: Mapped[str] = mapped_column(ForeignKey("work_groups.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # м², м³, шт, п.м.
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    
    # Связи
    group: Mapped["WorkGroup"] = relationship(back_populates="work_types")
    tech_sequence_items: Mapped[List["TechSequenceItem"]] = relationship(back_populates="work_type")


class TechSequenceItem(Base):
    """Элемент технологической последовательности для конкретного корпуса"""
    __tablename__ = "tech_sequence_items"
    
    housing_id: Mapped[str] = mapped_column(ForeignKey("housings.id"))
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id"))
    
    order: Mapped[int] = mapped_column(Integer, nullable=False)  # Порядок в последовательности
    depends_on: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)  # UUID других work_type_id
    dependency_type: Mapped[DependencyType] = mapped_column(String(20), default=DependencyType.FINISH_TO_START)
    lag_days: Mapped[int] = mapped_column(Integer, default=0)  # Задержка после предшествующей работы
    
    estimated_days: Mapped[int] = mapped_column(Integer, nullable=False)  # Нормативная длительность на секцию×этаж
    daily_norm_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)  # Норма выработки на день
    total_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)  # Общий объём на секцию×этаж
    
    # Связи
    housing: Mapped["Housing"] = relationship()
    work_type: Mapped["WorkType"] = relationship(back_populates="tech_sequence_items")