from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from src.api.schemes import HousingBaseFilters, IDMixinSchema


class CreateContractorRequest(BaseModel):
    name: str
    short_name: str
    inn: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class UpdateContractorRequest(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    inn: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ContractorSchema(IDMixinSchema):
    model_config = ConfigDict(from_attributes=True)

    name: str
    short_name: str
    inn: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ContractorFilters(HousingBaseFilters):
    search: Optional[str] = Query(None, description="Search in name, inn")
