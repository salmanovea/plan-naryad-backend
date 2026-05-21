from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import (
    ContractorBaseFilters,
    HousingBaseFilters,
    IDMixinSchema,
)
from src.models.dbo.tables.plan import PlanSource, PlanStatus


class GeneratePlanRequest(BaseModel):
    date: date
    housing_id: UUID


class ConfirmPlanRequest(BaseModel):
    confirmed_by: str = "rs-user"
    comment: Optional[str] = None


class AdjustPlanChange(BaseModel):
    field: str
    new_value: str


class AdjustPlanRequest(BaseModel):
    changes: List[AdjustPlanChange] = []
    reason: str = ""
    adjusted_by: str = "rs-user"


class CreatePlanItemRequest(BaseModel):
    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_type_id: UUID
    contractor_id: UUID
    planned_volume: Decimal
    unit: str
    source: PlanSource = PlanSource.MANUAL
    status: PlanStatus = PlanStatus.DRAFT


class PlanItemSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    date: date
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_type_id: UUID
    contractor_id: UUID
    planned_volume: Decimal
    unit: str
    rs_confirmed: bool = False
    source: Optional[str] = None
    status: Optional[str] = None
    work_name: Optional[str] = None
    section_name: Optional[str] = None
    floor_number: Optional[str] = None
    contractor_name: Optional[str] = None


class GeneratePlanResponse(BaseModel):
    items: List[PlanItemSchema]
    count: int
    message: str
    reasons: List[str] = []


class DailyPlanResponse(BaseModel):
    date: date
    housing_id: UUID
    housing_name: Optional[str] = None
    total_items: int = 0
    items: List[PlanItemSchema] = []


class ContractorPlanResponse(BaseModel):
    date: date
    contractor_id: UUID
    contractor_name: Optional[str] = None
    housing_id: Optional[UUID] = None
    items: List[PlanItemSchema] = []
    total_items: int = 0


class RSStatsResponse(BaseModel):
    rs_user_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    total_plans: int = 0
    total_adjustments: int = 0
    deviation_rate: Decimal = Decimal("0")
    top_adjustment_reasons: list = []


class PlanFilters(HousingBaseFilters, ContractorBaseFilters):
    date_from: Optional[date] = Query(None, description="Filter by date from (inclusive)")
    date_to: Optional[date] = Query(None, description="Filter by date to (inclusive)")
    status: Optional[str] = Query(None, description="Filter by plan status")
