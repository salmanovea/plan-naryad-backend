from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import HousingBaseFilters, IDMixinSchema


class AcknowledgeAlertRequest(BaseModel):
    acknowledged: bool = True
    acknowledged_by: str


class AlertSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    alert_type: str
    level: str
    date: date
    housing_id: UUID
    contractor_id: Optional[UUID] = None
    recipient_role: Optional[str] = None
    message: str
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    escalation_level: int = 0
    escalated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # enriched
    housing_name: Optional[str] = None
    contractor_name: Optional[str] = None


class GenerateAlertsRequest(BaseModel):
    housing_id: UUID
    alert_date: date


class GenerateAlertsResponse(BaseModel):
    generated: int
    alerts: List[AlertSchema]


class EscalationCheckResponse(BaseModel):
    escalated_count: int


class AlertFilters(HousingBaseFilters):
    date_from: Optional[date] = Query(None, description="Filter by date from (inclusive)")
    date_to: Optional[date] = Query(None, description="Filter by date to (inclusive)")
    alert_type: Optional[str] = Query(None, description="Filter by alert type (A01-A23)")
    level: Optional[str] = Query(None, description="Filter by alert level")
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledged status")
    recipient_role: Optional[str] = Query(None, description="Filter by recipient role")
