from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import (
    ContractorBaseFilters,
    HousingBaseFilters,
    IDMixinSchema,
    WorkTypeBaseFilters,
)
from src.models.dbo.tables.fact import FactSource


class CreateWorkFactRequest(BaseModel):
    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_type_id: UUID
    contractor_id: UUID
    actual_volume: Decimal
    unit: str
    submitted_by: Optional[str] = None
    source: FactSource = FactSource.CONTRACTOR_WEB
    comment: Optional[str] = None


class UpdateWorkFactRequest(BaseModel):
    actual_volume: Optional[Decimal] = None
    comment: Optional[str] = None


class WorkFactSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_type_id: UUID
    contractor_id: UUID
    actual_volume: Decimal
    unit: str
    submitted_by: Optional[str] = None
    source: Optional[str] = None
    comment: Optional[str] = None
    submitted_at: Optional[datetime] = None


class WorkFactFilters(HousingBaseFilters, ContractorBaseFilters, WorkTypeBaseFilters):
    date_from: Optional[date] = Query(None, description="Filter by date from (inclusive)")
    date_to: Optional[date] = Query(None, description="Filter by date to (inclusive)")
