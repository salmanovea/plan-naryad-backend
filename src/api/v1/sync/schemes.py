"""
Request schemas for /api/v1/sync/import/* endpoints.

These let an external script (e.g. xlsx dump from Raport) push reference data
into the local DB without going through the live Raport API. Parents are
referenced by their Raport id (`*_raport_id`); the service resolves them to
local UUIDs at upsert time.
"""

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SyncEntity(str, Enum):
    """Reference entities that the unified sync/import dispatcher understands.

    Granular (per local table) so it works for both channels:
      - live `/sync` groups them into the hierarchical fetch operations
        (any of projects/construction_objects/housings/sections/floors →
        one `sync_objects` traversal; work_kinds/works → one `sync_work_catalog`);
      - offline `/sync/import` maps each to its own `import_*` handler.

    Terminology (see docs/sync-mapping.md §3): WORK_KINDS («Виды работ») is the
    local `work_groups` table (= Raport WorkType); WORKS («Работы») is the local
    `work_types` table (= Raport Work).
    """

    USERS = "users"
    CONTRACTORS = "contractors"
    CONTRACTS = "contracts"
    PROJECTS = "projects"
    CONSTRUCTION_OBJECTS = "construction_objects"
    HOUSINGS = "housings"
    SECTIONS = "sections"
    FLOORS = "floors"
    WORK_KINDS = "work_kinds"
    WORKS = "works"
    ASSIGNMENTS = "assignments"
    TECH_SEQUENCE = "tech_sequence"


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


class ImportContractItem(BaseModel):
    raport_id: str
    contractor_raport_id: Optional[str] = None  # resolved to a local contractor id; null if unknown
    name: Optional[str] = None
    subject: Optional[str] = None
    is_warranty_letter: bool = False


class ImportContractsRequest(BaseModel):
    items: List[ImportContractItem]


class ImportUserItem(BaseModel):
    raport_id: str
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    shown_name: Optional[str] = None
    email: Optional[str] = None
    is_external: bool = False
    groups: List[str] = Field(default_factory=list)
    project_ids: List[str] = Field(default_factory=list)
    contractor_ids: List[str] = Field(default_factory=list)


class ImportUsersRequest(BaseModel):
    items: List[ImportUserItem]


class ImportResultSchema(BaseModel):
    """Counts returned by every /sync/import/* endpoint."""

    received: int = Field(..., description="Number of items in the payload")
    upserted: int = Field(..., description="Number of items written to DB")
    missing_parents: int = Field(0, description="Items skipped because parent raport_id was not found")


class SyncRequest(BaseModel):
    """Body for the unified live `POST /sync`. `entities` is optional — omit or
    leave empty to sync every supported entity."""

    entities: Optional[List[SyncEntity]] = Field(
        default=None,
        description="Subset of entities to sync; null/empty means all.",
    )


class SyncImportRequest(BaseModel):
    """Body for the unified offline `POST /sync/import`.

    `entities` selects which entities to process; null/empty means "process
    every entity for which a payload list is provided". Lists left as null are
    skipped regardless of `entities`.
    """

    entities: Optional[List[SyncEntity]] = None
    users: Optional[List[ImportUserItem]] = None
    contractors: Optional[List[ImportContractorItem]] = None
    contracts: Optional[List[ImportContractItem]] = None
    projects: Optional[List[ImportProjectItem]] = None
    construction_objects: Optional[List[ImportConstructionObjectItem]] = None
    housings: Optional[List[ImportHousingItem]] = None
    sections: Optional[List[ImportSectionItem]] = None
    floors: Optional[List[ImportFloorItem]] = None
    work_kinds: Optional[List[ImportWorkGroupItem]] = None  # «Виды работ» → work_groups
    works: Optional[List[ImportWorkTypeItem]] = None  # «Работы» → work_types
