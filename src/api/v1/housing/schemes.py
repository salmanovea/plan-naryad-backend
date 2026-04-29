from typing import List, Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import IDMixinSchema


class CreateHousingRequest(BaseModel):
    name: str
    complex_name: str
    description: Optional[str] = None


class UpdateHousingRequest(BaseModel):
    name: Optional[str] = None
    complex_name: Optional[str] = None
    description: Optional[str] = None


class HousingSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    name: str
    complex_name: str
    description: Optional[str] = None


class CreateSectionRequest(BaseModel):
    housing_id: UUID
    name: str
    section_number: int
    description: Optional[str] = None


class UpdateSectionRequest(BaseModel):
    name: Optional[str] = None
    section_number: Optional[int] = None
    description: Optional[str] = None


class SectionSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    housing_id: UUID
    name: str
    section_number: int
    description: Optional[str] = None


class CreateFloorRequest(BaseModel):
    section_id: UUID
    floor_number: int
    name: Optional[str] = None
    description: Optional[str] = None


class UpdateFloorRequest(BaseModel):
    floor_number: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None


class FloorSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    section_id: UUID
    floor_number: int
    name: Optional[str] = None
    description: Optional[str] = None


class FloorInStructure(BaseModel):
    floor_id: UUID
    floor_number: int


class SectionInStructure(BaseModel):
    section_id: UUID
    section_name: str
    floors: List[FloorInStructure] = []


class HousingStructureSchema(BaseModel):
    housing_id: UUID
    housing_name: str
    complex_name: str
    sections: List[SectionInStructure] = []


class HousingFilters(BaseModel):
    search: Optional[str] = Query(None, description="Search in name, complex_name")
    complex_name: Optional[str] = Query(None, description="Filter by complex name")
