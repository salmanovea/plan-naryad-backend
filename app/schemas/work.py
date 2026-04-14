from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from ..models.work import DependencyType


class WorkGroupBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    order: int = 0


class WorkGroup(WorkGroupBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID


class WorkTypeBase(BaseModel):
    group_id: UUID
    name: str
    code: str
    unit: str
    description: Optional[str] = None


class WorkType(WorkTypeBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    group: Optional[WorkGroup] = None


class TechSequenceItemBase(BaseModel):
    housing_id: UUID
    work_type_id: UUID
    order: int
    depends_on: List[str] = []
    dependency_type: DependencyType = DependencyType.FINISH_TO_START
    lag_days: int = 0
    estimated_days: int
    daily_norm_volume: Decimal
    total_volume: Decimal


class TechSequenceItem(TechSequenceItemBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    work_type: Optional[WorkType] = None


class TechSequence(BaseModel):
    """Техпоследовательность для конкретного корпуса"""
    housing_id: UUID
    housing_name: str
    sequence: List[dict]


class WorkTypeCreate(WorkTypeBase):
    pass


class TechSequenceItemCreate(TechSequenceItemBase):
    pass