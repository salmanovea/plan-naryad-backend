from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import IDMixinSchema, WorkGroupBaseFilters, WorkSetBaseFilters, WorkTypeBaseFilters
from src.models.dbo.tables.work import FloorSortingDirection, PlanningType


class CreateWorkSetRequest(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    order: int = 0


class UpdateWorkSetRequest(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None


class WorkSetSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    name: str
    code: str
    description: Optional[str] = None
    order: int


class CreateWorkGroupRequest(BaseModel):
    work_set_id: Optional[UUID] = None
    name: str
    code: str
    description: Optional[str] = None
    order: int = 0


class UpdateWorkGroupRequest(BaseModel):
    work_set_id: Optional[UUID] = None
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None


class WorkGroupSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    work_set_id: Optional[UUID] = None
    name: str
    code: str
    description: Optional[str] = None
    order: int


class CreateWorkTypeRequest(BaseModel):
    work_group_id: Optional[UUID] = None
    name: str
    code: str
    description: Optional[str] = None
    order: int = 0


class UpdateWorkTypeRequest(BaseModel):
    work_group_id: Optional[UUID] = None
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None


class WorkTypeSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    work_group_id: Optional[UUID] = None
    name: str
    code: str
    description: Optional[str] = None
    order: int


class CreateWorkRequest(BaseModel):
    work_type_id: UUID
    name: str
    code: str
    unit: str
    description: Optional[str] = None


class UpdateWorkRequest(BaseModel):
    work_type_id: Optional[UUID] = None
    name: Optional[str] = None
    code: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None


class WorkSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    work_type_id: UUID
    name: str
    code: str
    unit: str
    description: Optional[str] = None


class CreateTechSequenceItemRequest(BaseModel):
    housing_id: UUID
    section_id: Optional[UUID] = None
    work_id: UUID
    order: int
    depends_on: List[UUID] = []
    depends_on_ss: List[UUID] = []
    lag_days: int = 0
    planning_type: Optional[PlanningType] = None
    floor_sorting_direction: Optional[FloorSortingDirection] = None
    lag_between_floors: Optional[int] = None
    estimated_days: int
    daily_norm_volume: Decimal
    total_volume: Decimal


class TechSequenceItemSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    housing_id: UUID
    section_id: Optional[UUID] = None
    work_id: UUID
    order: int
    depends_on: List[str] = []
    depends_on_ss: List[str] = []
    lag_days: int
    planning_type: Optional[PlanningType] = None
    floor_sorting_direction: Optional[FloorSortingDirection] = None
    lag_between_floors: Optional[int] = None
    estimated_days: int
    daily_norm_volume: Decimal
    total_volume: Decimal
    work: Optional[WorkSchema] = None


class TechSequenceSchema(BaseModel):
    housing_id: UUID
    housing_name: str
    sequence: List[TechSequenceItemSchema] = []


class WorkSetFilters(BaseModel):
    search: Optional[str] = Query(None, description="Search in name, code")


class WorkGroupFilters(WorkSetBaseFilters):
    search: Optional[str] = Query(None, description="Search in name, code")


class WorkTypeFilters(WorkGroupBaseFilters):
    search: Optional[str] = Query(None, description="Search in name, code")


class WorkFilters(WorkTypeBaseFilters):
    search: Optional[str] = Query(None, description="Search in name, code")
