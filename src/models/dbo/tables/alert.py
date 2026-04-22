from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor
    from src.models.dbo.tables.housing import Housing


class AlertType(str, Enum):
    A01 = "A01"
    A02 = "A02"
    A03 = "A03"
    A04 = "A04"
    A05 = "A05"
    A06 = "A06"
    A07 = "A07"
    A10 = "A10"
    A11 = "A11"
    A12 = "A12"
    A13 = "A13"
    A14 = "A14"
    A15 = "A15"
    A20 = "A20"
    A21 = "A21"
    A22 = "A22"
    A23 = "A23"


class AlertLevel(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class RecipientRole(str, Enum):
    RS = "RS"
    DS = "DS"
    DP = "DP"
    CONTRACTOR = "CONTRACTOR"
    ADMIN = "ADMIN"


class Alert(IDMixin, Base):
    """Notification / alert record."""

    __tablename__ = "alerts"

    alert_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    housing_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("housings.id", name="fk_alerts_housing_id"),
        index=True,
    )
    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("contractors.id", name="fk_alerts_contractor_id"),
        index=True,
    )
    rs_user_id: Mapped[Optional[str]] = mapped_column(String(255))

    recipient_id: Mapped[Optional[str]] = mapped_column(String(255))
    recipient_role: Mapped[str] = mapped_column(String(20), nullable=False)

    message: Mapped[str] = mapped_column(Text, nullable=False)

    channels_sent: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(255))

    escalation_level: Mapped[int] = mapped_column(Integer, default=1)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    housing: Mapped[Optional["Housing"]] = relationship()  # type: ignore[name-defined]
    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]
