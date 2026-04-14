from decimal import Decimal
from sqlalchemy import String, Date, Numeric, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import date, datetime
from enum import Enum

from ..database import Base


class PlanSource(str, Enum):
    AUTO = "auto"  # Автогенерация
    MANUAL = "manual"  # Ручное добавление РС
    ADJUSTED = "adjusted"  # Скорректировано РС


class PlanStatus(str, Enum):
    DRAFT = "draft"  # Черновик (не подтверждён РС)
    CONFIRMED = "confirmed"  # Подтверждён РС
    CANCELLED = "cancelled_by_rs"  # Отменён РС


class PlanItem(Base):
    """Строка план-наряда"""
    __tablename__ = "plan_items"
    
    date: Mapped[date] = mapped_column(Date, nullable=False)
    housing_id: Mapped[str] = mapped_column(ForeignKey("housings.id"))
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"))
    floor_id: Mapped[str] = mapped_column(ForeignKey("floors.id"))
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id"))
    contractor_id: Mapped[str] = mapped_column(ForeignKey("contractors.id"))
    
    planned_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # Дублируем для удобства
    
    rs_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    rs_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rs_confirmed_by: Mapped[Optional[str]] = mapped_column(String(255))  # user_id РС
    
    source: Mapped[PlanSource] = mapped_column(String(20), default=PlanSource.AUTO)
    status: Mapped[PlanStatus] = mapped_column(String(20), default=PlanStatus.DRAFT)
    
    # Связи
    housing: Mapped["Housing"] = relationship()
    section: Mapped["Section"] = relationship() 
    floor: Mapped["Floor"] = relationship()
    work_type: Mapped["WorkType"] = relationship()
    contractor: Mapped["Contractor"] = relationship()
    adjustments: Mapped[list["PlanAdjustment"]] = relationship(back_populates="plan_item", cascade="all, delete-orphan")


class PlanAdjustment(Base):
    """История корректировок план-наряда РС"""
    __tablename__ = "plan_adjustments"
    
    plan_item_id: Mapped[str] = mapped_column(ForeignKey("plan_items.id"))
    original_field: Mapped[str] = mapped_column(String(50), nullable=False)  # floor_id, volume, work_type_id
    original_value: Mapped[str] = mapped_column(String(255), nullable=False)
    new_value: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)  # Обязательный комментарий
    
    adjusted_by: Mapped[str] = mapped_column(String(255), nullable=False)  # user_id РС
    adjusted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    plan_item: Mapped["PlanItem"] = relationship(back_populates="adjustments")