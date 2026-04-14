from sqlalchemy import String, Date, ForeignKey, DateTime, Boolean, Integer, ARRAY, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from datetime import date, datetime
from enum import Enum

from ..database import Base


class AlertType(str, Enum):
    # Операционные (ежедневные)
    A01 = "A01"  # План-наряд сформирован
    A02 = "A02"  # РС не подтвердил план-наряд
    A03 = "A03"  # План-наряд отправлен подрядчику
    A04 = "A04"  # Напоминание: подай факт
    A05 = "A05"  # Подрядчик не подал факт
    A06 = "A06"  # Сводка дня готова
    A07 = "A07"  # Критическое отклонение
    
    # Аналитические
    A10 = "A10"  # Хроническое невыполнение
    A11 = "A11"  # Хронический отказ от факта
    A12 = "A12"  # Работа не по плану
    A13 = "A13"  # РС не управляет
    A14 = "A14"  # Высокое отклонение РС от эталона
    A15 = "A15"  # Просрочка по календарному плану
    
    # Системные
    A20 = "A20"  # Генерация не запустилась
    A21 = "A21"  # Сверка не запустилась
    A22 = "A22"  # Нет техпоследовательности
    A23 = "A23"  # Нет привязки подрядчика


class AlertLevel(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class RecipientRole(str, Enum):
    RS = "RS"  # Руководитель строительства
    DS = "DS"  # Директор строительства
    DP = "DP"  # Директор проекта
    CONTRACTOR = "CONTRACTOR"  # Подрядчик
    ADMIN = "ADMIN"  # Администратор системы


class Alert(Base):
    """Алерт/уведомление"""
    __tablename__ = "alerts"
    
    alert_type: Mapped[AlertType] = mapped_column(String(10), nullable=False)
    level: Mapped[AlertLevel] = mapped_column(String(10), nullable=False)
    
    date: Mapped[date] = mapped_column(Date, nullable=False)
    housing_id: Mapped[Optional[str]] = mapped_column(ForeignKey("housings.id"))
    contractor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("contractors.id"))
    rs_user_id: Mapped[Optional[str]] = mapped_column(String(255))  # ID пользователя-РС
    
    recipient_id: Mapped[str] = mapped_column(String(255), nullable=False)  # ID получателя
    recipient_role: Mapped[RecipientRole] = mapped_column(String(20), nullable=False)
    
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Каналы доставки
    channels_sent: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)  # ['push', 'bot', 'email']
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Подтверждение
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Эскалация
    escalation_level: Mapped[int] = mapped_column(Integer, default=1)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Связи
    housing: Mapped[Optional["Housing"]] = relationship()
    contractor: Mapped[Optional["Contractor"]] = relationship()