from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import Query
from pydantic import ConfigDict

from src.api.schemes import (
    ContractorBaseFilters,
    HousingBaseFilters,
    IDMixinSchema,
    WorkBaseFilters,
)


class WorkFactSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    work_date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_id: UUID
    contractor_id: Optional[UUID] = None
    percent: Optional[Decimal] = None
    unit: Optional[str] = None
    work_cell_contractor_id: Optional[UUID] = None
    work_cell_id: Optional[UUID] = None
    submitted_by: Optional[str] = None
    source: Optional[str] = None
    comment: Optional[str] = None
    submitted_at: Optional[datetime] = None


class WorkFactFilters(HousingBaseFilters, ContractorBaseFilters, WorkBaseFilters):
    work_date__gte: Optional[date] = Query(None, description="Filter by work date from (inclusive)")
    work_date__lte: Optional[date] = Query(None, description="Filter by work date to (inclusive)")
