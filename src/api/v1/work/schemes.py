from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import IDMixinSchema, WorkGroupBaseFilters
from src.models.dbo.tables.work import DependencyType


class CreateWorkGroupRequest(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    order: int = 0


class UpdateWorkGroupRequest(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None


class WorkGroupSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    name: str
    code: str
    description: Optional[str] = None
    order: int


class CreateWorkTypeRequest(BaseModel):
    group_id: UUID
    name: str
    code: str
    unit: str
    description: Optional[str] = None


class UpdateWorkTypeRequest(BaseModel):
    group_id: Optional[UUID] = None
    name: Optional[str] = None
    code: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None


class WorkTypeSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    group_id: UUID
    name: str
    code: str
    unit: str
    description: Optional[str] = None


class CreateTechSequenceItemRequest(BaseModel):
    housing_id: UUID
    work_type_id: UUID
    order: int
    dependency_type: DependencyType = DependencyType.FINISH_TO_START
    lag_days: int = 0
    estimated_days: int
    daily_norm_volume: Decimal
    total_volume: Decimal


class TechSequenceItemSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    housing_id: UUID
    work_type_id: UUID
    order: int
    dependency_type: DependencyType
    lag_days: int
    estimated_days: int
    daily_norm_volume: Decimal
    total_volume: Decimal
    work_type: Optional[WorkTypeSchema] = None


class TechSequenceSchema(BaseModel):
    housing_id: UUID
    housing_name: str
    sequence: List[TechSequenceItemSchema] = []


class WorkFilters(WorkGroupBaseFilters):
    search: Optional[str] = Query(None, description="Search in name, code")
