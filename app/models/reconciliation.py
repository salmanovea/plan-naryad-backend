from decimal import Decimal
from sqlalchemy import String, Date, Numeric, Boolean, ForeignKey, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Any
from datetime import date, datetime
from enum import Enum

from ..database import Base


class ReconciliationStatus(str, Enum):
    DONE_FULL = "DONE_FULL"  # Выполнено полностью (≥95%)
    DONE_PARTIAL = "DONE_PARTIAL"  # Выполнено частично (0-95%)
    DONE_OVER = "DONE_OVER"  # Перевыполнение (>105%)
    NOT_DONE = "NOT_DONE"  # Не выполнено (план есть, факт = 0)
    NO_REPORT = "NO_REPORT"  # Факт не подан
    UNPLANNED = "UNPLANNED"  # Внеплановая работа


class ReconciliationPattern(str, Enum):
    WRONG_LOCATION = "WRONG_LOCATION"  # Работа не там
    WRONG_WORK_TYPE = "WRONG_WORK_TYPE"  # Работа не та
    CHRONIC_NO_REPORT = "CHRONIC_NO_REPORT"  # Систематически не подаёт факт
    CHRONIC_UNDERPERFORM = "CHRONIC_UNDERPERFORM"  # Систематически не выполняет


class ReconciliationResult(Base):
    """Результат сверки план/факт по одной строке"""
    __tablename__ = "reconciliation_results"
    
    date: Mapped[date] = mapped_column(Date, nullable=False)
    housing_id: Mapped[str] = mapped_column(ForeignKey("housings.id"))
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"))
    floor_id: Mapped[str] = mapped_column(ForeignKey("floors.id"))
    work_type_id: Mapped[str] = mapped_column(ForeignKey("work_types.id"))
    contractor_id: Mapped[str] = mapped_column(ForeignKey("contractors.id"))
    
    # Объёмы
    planned_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    actual_volume: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    completion_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # actual / planned
    
    # Результат сверки
    status: Mapped[ReconciliationStatus] = mapped_column(String(20), nullable=False)
    pattern: Mapped[Optional[ReconciliationPattern]] = mapped_column(String(30))
    
    # Связь с исходными записями
    plan_item_id: Mapped[Optional[str]] = mapped_column(ForeignKey("plan_items.id"))
    work_fact_id: Mapped[Optional[str]] = mapped_column(ForeignKey("work_facts.id"))
    
    # Время подачи факта
    fact_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    fact_is_late: Mapped[bool] = mapped_column(Boolean, default=False)  # submitted_at > 20:00
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    housing: Mapped["Housing"] = relationship()
    section: Mapped["Section"] = relationship() 
    floor: Mapped["Floor"] = relationship()
    work_type: Mapped["WorkType"] = relationship()
    contractor: Mapped["Contractor"] = relationship()
    plan_item: Mapped[Optional["PlanItem"]] = relationship()
    work_fact: Mapped[Optional["WorkFact"]] = relationship()


class DailySummary(Base):
    """Сводка дня по корпусу"""
    __tablename__ = "daily_summaries"
    
    date: Mapped[date] = mapped_column(Date, nullable=False)
    housing_id: Mapped[str] = mapped_column(ForeignKey("housings.id"))
    
    # Итого строк по статусам
    total_planned: Mapped[int] = mapped_column(Integer, default=0)
    total_done_full: Mapped[int] = mapped_column(Integer, default=0)
    total_done_partial: Mapped[int] = mapped_column(Integer, default=0)
    total_done_over: Mapped[int] = mapped_column(Integer, default=0)
    total_not_done: Mapped[int] = mapped_column(Integer, default=0)
    total_no_report: Mapped[int] = mapped_column(Integer, default=0)
    total_unplanned: Mapped[int] = mapped_column(Integer, default=0)
    
    # Проценты
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)  # (done_full + done_over) / planned
    weighted_completion: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)  # Взвешенный по объёмам
    submission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)  # % подрядчиков, подавших факт
    
    # JSON с деталями по подрядчикам и алертами
    contractor_details: Mapped[Optional[Any]] = mapped_column(JSON)
    alerts: Mapped[Optional[Any]] = mapped_column(JSON)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    housing: Mapped["Housing"] = relationship()