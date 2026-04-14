from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from uuid import UUID


class FloorBase(BaseModel):
    section_id: UUID
    floor_number: int
    name: Optional[str] = None
    description: Optional[str] = None


class Floor(FloorBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID


class SectionBase(BaseModel):
    housing_id: UUID
    name: str
    section_number: int
    description: Optional[str] = None


class Section(SectionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    # floors: List[Floor] = []  # Removed to avoid lazy loading issues


class HousingBase(BaseModel):
    name: str
    complex_name: str
    description: Optional[str] = None


class Housing(HousingBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    # sections: List[Section] = []  # Removed to avoid lazy loading issues


class HousingStructure(BaseModel):
    """Полная структура корпуса для API"""
    housing_id: UUID
    housing_name: str
    complex_name: str
    sections: List[dict] = []


class HousingCreate(HousingBase):
    pass


class HousingUpdate(BaseModel):
    name: Optional[str] = None
    complex_name: Optional[str] = None
    description: Optional[str] = None