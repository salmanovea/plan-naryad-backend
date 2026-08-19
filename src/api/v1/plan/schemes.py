from datetime import date as date_type
from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from src.api.schemes import (
    ContractorBaseFilters,
    FloorBaseFilters,
    HousingBaseFilters,
    IDMixinSchema,
    ProjectBaseFilters,
    SectionBaseFilters,
    WorkBaseFilters,
)


class GeneratePlanRequest(BaseModel):
    date: Optional[date_type] = None
    housing_id: UUID
    section_id: Optional[UUID] = None
    force: bool = False


class ConfirmPlanRequest(BaseModel):
    confirmed_by: str = "rs-user"
    comment: Optional[str] = None


class CreatePlanItemRequest(BaseModel):
    """Manual addition. No volume — the spec removed the field («Поле Объем убираем»)."""

    date: date_type
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_id: UUID
    contractor_id: UUID


class PlanItemSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    date: date_type
    housing_id: UUID
    section_id: UUID
    floor_id: UUID
    work_id: UUID
    contractor_id: UUID
    source_percent: Optional[Decimal] = None
    work_cell_contractor_id: Optional[UUID] = None
    work_cell_id: Optional[UUID] = None
    rs_confirmed: bool = False
    source: Optional[str] = None
    status: Optional[str] = None
    work_name: Optional[str] = None
    work_type_name: Optional[str] = None
    work_group_name: Optional[str] = None
    work_set_name: Optional[str] = None
    section_name: Optional[str] = None
    floor_name: Optional[str] = None
    floor_number: Optional[int] = None
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


class TransferPlanRequest(BaseModel):
    """Hand a day over to the contractors — normally called by the scheduler at the cutoff."""

    date: date_type
    housing_id: Optional[UUID] = None
    section_id: Optional[UUID] = None


class NamedRef(BaseModel):
    id: UUID
    name: str


class AvailableWorkRow(BaseModel):
    """One row of the «Этап → Комплекс → Вид → Работа» dropdown."""

    work_set: Optional[NamedRef] = None
    work_group: Optional[NamedRef] = None
    work_type: Optional[NamedRef] = None
    work: NamedRef


class DailyAssignmentRow(BaseModel):
    """One cell Raport should keep active in the «Задание на день» view.

    Every reference is a **Raport** id, not a local one: Raport is the consumer and only
    knows its own entities. `work_cell_contractor_id` is the key it needs — the chessboard is
    split by contractor at that grain (Р0); the rest is there so a cell can still be located
    if the position was created before Raport had the cell.
    """

    work_cell_contractor_id: Optional[UUID] = None
    work_cell_id: Optional[UUID] = None
    section_id: Optional[str] = None
    floor_id: Optional[str] = None
    work_id: Optional[str] = None
    contractor_id: Optional[str] = None
    plan_item_id: UUID
    status: str


class PlanFilters(
    HousingBaseFilters,
    ContractorBaseFilters,
    SectionBaseFilters,
    FloorBaseFilters,
    WorkBaseFilters,
    ProjectBaseFilters,
):
    """Table filters: the spec wants multi-select with «select all» on every column."""

    date_from: Optional[date_type] = Query(None, description="Filter by date from (inclusive)")
    date_to: Optional[date_type] = Query(None, description="Filter by date to (inclusive)")
    status: Optional[str] = Query(None, description="Filter by plan status")
    status__in: Optional[List[str]] = Field(Query(None, description="Filter by several statuses"))
    source__in: Optional[List[str]] = Field(Query(None, description="Filter by several sources"))
