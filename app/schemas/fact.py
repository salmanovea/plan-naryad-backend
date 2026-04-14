from pydantic import BaseModel, Field
from datetime import date, datetime
from uuid import UUID
from typing import Optional
from decimal import Decimal


class FactBase(BaseModel):
    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_type_id: UUID
    contractor_id: UUID
    actual_volume: Decimal
    unit: str
    submitted_by: Optional[str] = None
    source: Optional[str] = "contractor_web"
    comment: Optional[str] = None


class FactCreate(FactBase):
    pass


class FactUpdate(BaseModel):
    actual_volume: Optional[Decimal] = None
    comment: Optional[str] = None


class Fact(FactBase):
    id: UUID
    submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FactWithDetails(Fact):
    housing_name: Optional[str] = None
    section_name: Optional[str] = None
    work_name: Optional[str] = None
    contractor_name: Optional[str] = None
