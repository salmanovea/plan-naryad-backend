from pydantic import BaseModel, Field
from datetime import date, datetime
from uuid import UUID
from typing import Optional
from enum import Enum

class AlertType(str, Enum):
    A01 = "A01"
    A02 = "A02"
    A03 = "A03"
    A04 = "A04"
    A05 = "A05"
    A06 = "A06"
    A07 = "A07"
    A08 = "A08"
    A09 = "A09"
    A10 = "A10"
    A11 = "A11"
    A12 = "A12"
    A13 = "A13"
    A14 = "A14"
    A15 = "A15"
    A16 = "A16"
    A17 = "A17"
    A18 = "A18"
    A19 = "A19"
    A20 = "A20"
    A21 = "A21"
    A22 = "A22"
    A23 = "A23"

class AlertLevel(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

class AlertBase(BaseModel):
    alert_type: AlertType
    level: AlertLevel
    date: date
    housing_id: UUID
    contractor_id: Optional[UUID] = None
    rs_user_id: Optional[str] = None
    recipient_id: Optional[str] = None
    recipient_role: Optional[str] = None
    message: str
    channels_sent: list[str] = []
    sent_at: Optional[datetime] = None
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    escalation_level: int = Field(0, ge=0, le=3)
    escalated_at: Optional[datetime] = None

class AlertCreate(AlertBase):
    pass

class AlertUpdate(BaseModel):
    acknowledged: Optional[bool] = None
    acknowledged_by: Optional[str] = None
    channels_sent: Optional[list[str]] = None

class AlertAcknowledge(BaseModel):
    acknowledged: bool = True
    acknowledged_by: str

class Alert(AlertBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class AlertWithDetails(Alert):
    housing_name: Optional[str] = None
    contractor_name: Optional[str] = None
    rs_user_name: Optional[str] = None
    recipient_name: Optional[str] = None