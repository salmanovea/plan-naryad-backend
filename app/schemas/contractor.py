from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from uuid import UUID


class ContractorBase(BaseModel):
    name: str
    short_name: str
    inn: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class Contractor(ContractorBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID


class ContractorAssignmentBase(BaseModel):
    contractor_id: UUID
    housing_id: UUID
    section_id: Optional[UUID] = None
    work_group_id: Optional[UUID] = None
    work_type_ids: List[str] = []


class ContractorAssignment(ContractorAssignmentBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    contractor: Optional[Contractor] = None


class ContractorAssignmentsResponse(BaseModel):
    """Привязки подрядчиков для конкретного корпуса"""
    housing_id: UUID
    assignments: List[ContractorAssignment]


class ContractorCreate(ContractorBase):
    pass


class ContractorUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    inn: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ContractorAssignmentCreate(ContractorAssignmentBase):
    pass