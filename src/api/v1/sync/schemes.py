"""
Request schemas for /api/v1/sync/import/* endpoints.

These let an external script (e.g. xlsx dump from Raport) push reference data
into the local DB without going through the live Raport API. Parents are
referenced by their Raport id (`*_raport_id`); the service resolves them to
local UUIDs at upsert time.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class ImportProjectItem(BaseModel):
    raport_id: str
    name: str
    project_class: str = "Комфорт"
    description: Optional[str] = None


class ImportProjectsRequest(BaseModel):
    items: List[ImportProjectItem]


class ImportConstructionObjectItem(BaseModel):
    raport_id: str
    project_raport_id: str
    name: str
    description: Optional[str] = None
    planned_end_date: Optional[date] = None


class ImportConstructionObjectsRequest(BaseModel):
    items: List[ImportConstructionObjectItem]


class ImportHousingItem(BaseModel):
    raport_id: str
    name: str
    complex_name: str
    construction_object_raport_id: Optional[str] = None
    description: Optional[str] = None


class ImportHousingsRequest(BaseModel):
    items: List[ImportHousingItem]


class ImportSectionItem(BaseModel):
    raport_id: str
    housing_raport_id: str
    name: str
    section_number: int = 0
    description: Optional[str] = None


class ImportSectionsRequest(BaseModel):
    items: List[ImportSectionItem]


class ImportFloorItem(BaseModel):
    raport_id: str
    section_raport_id: str
    floor_number: int = 0
    name: Optional[str] = None
    description: Optional[str] = None


class ImportFloorsRequest(BaseModel):
    items: List[ImportFloorItem]


class ImportWorkGroupItem(BaseModel):
    raport_id: str
    name: str
    code: str
    description: Optional[str] = None


class ImportWorkGroupsRequest(BaseModel):
    items: List[ImportWorkGroupItem]


class ImportWorkTypeItem(BaseModel):
    raport_id: str
    work_group_raport_id: str
    name: str
    code: str
    unit: str = "шт"
    description: Optional[str] = None


class ImportWorkTypesRequest(BaseModel):
    items: List[ImportWorkTypeItem]


class ImportContractorItem(BaseModel):
    raport_id: str
    name: str
    short_name: Optional[str] = None  # falls back to name on the service side
    inn: Optional[str] = None
    description: Optional[str] = None


class ImportContractorsRequest(BaseModel):
    items: List[ImportContractorItem]


class ImportResultSchema(BaseModel):
    """Counts returned by every /sync/import/* endpoint."""

    received: int = Field(..., description="Number of items in the payload")
    upserted: int = Field(..., description="Number of items written to DB")
    missing_parents: int = Field(0, description="Items skipped because parent raport_id was not found")
