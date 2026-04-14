from decimal import Decimal
from sqlalchemy import String, Date, Numeric, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import date, datetime
from enum import Enum

from ..database import Base


class FactSource(str, Enum):
    CONTRACTOR_BOT = "contractor_bot"  # Подрядчик через бота
    CONTRACTOR_WEB = "contractor_web"  # Подрядчик через веб
    RS_WEB = "rs_web"  # РС внёс за подрядчика


class WorkFact(Base):
    """Факт выполнения работ"""
    __tablename__ = "work_facts"
    
    date: Mapped[date] = mapped_column(Date, nullable=False)
    housing_id: Mapped[str] = mapped_column(ForeignKey("housings.id"))
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"))
    floor_id: Mapped[str] = mapped_column(ForeignKey("floors.id"))
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id"))
    contractor_id: Mapped[str] = mapped_column(ForeignKey("contractors.id"))
    
    actual_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)  # user_id или contractor_id
    source: Mapped[FactSource] = mapped_column(String(20), default=FactSource.CONTRACTOR_WEB)
    
    # Дополнительная информация
    comment: Mapped[Optional[str]] = mapped_column(Text)
    photo_urls: Mapped[Optional[str]] = mapped_column(Text)  # JSON array в строке
    
    # Связи
    housing: Mapped["Housing"] = relationship()
    section: Mapped["Section"] = relationship() 
    floor: Mapped["Floor"] = relationship()
    work_type: Mapped["WorkType"] = relationship()
    contractor: Mapped["Contractor"] = relationship()