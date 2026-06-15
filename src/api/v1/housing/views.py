from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemes import (
    DataResponseSchema,
    ListDataResponseSchema,
    ResponseGroup,
)
from src.api.v1.housing.schemes import (
    CreateFloorRequest,
    CreateHousingRequest,
    CreateSectionRequest,
    FloorInStructure,
    FloorSchema,
    HousingFilters,
    HousingSchema,
    HousingStructureSchema,
    SectionInStructure,
    SectionSchema,
    UpdateFloorRequest,
    UpdateHousingRequest,
    UpdateSectionRequest,
)
from src.services.housing.service import HousingService, get_housing_service
from src.utils.helpers import catch_all_exceptions, get_responses, pagination_params
from src.api.schemes import PaginationParams

housing_router = APIRouter(prefix="/housings", tags=["Housing"])


@housing_router.get("/", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_housings(
    filters: HousingFilters = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    service: HousingService = Depends(get_housing_service),
) -> ListDataResponseSchema[HousingSchema]:
    filter_data = filters.model_dump(exclude_none=True)
    search_text = filter_data.pop("search", None)
    items = await service.housing_manager.search(
        search=search_text, order_by=["name"], pagination=pagination, **filter_data
    )
    total = await service.housing_manager.count(search=search_text, **filter_data)
    return ListDataResponseSchema[HousingSchema].create(
        list_data=[HousingSchema.model_validate(i) for i in items],
        pagination=pagination,
        total=total,
    )


@housing_router.get("/{housing_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_housing(
    housing_id: UUID,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[HousingSchema]:
    item = await service.housing_manager.get_by_id(housing_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Housing not found")
    return DataResponseSchema[HousingSchema](data=HousingSchema.model_validate(item))


@housing_router.get("/{housing_id}/structure", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def get_housing_structure(
    housing_id: UUID,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[HousingStructureSchema]:
    housing = await service.housing_manager.get_by_id(housing_id)
    if not housing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Housing not found")

    sections = await service.section_manager.search(housing_id=housing_id, order_by=["section_number"])
    section_list = []
    for section in sections:
        floors = await service.floor_manager.search(section_id=section.id, order_by=["floor_number"])
        section_list.append(
            SectionInStructure(
                section_id=section.id,
                section_name=section.name,
                floors=[FloorInStructure(floor_id=f.id, floor_number=f.floor_number, name=f.name) for f in floors],
            )
        )

    return DataResponseSchema[HousingStructureSchema](
        data=HousingStructureSchema(
            housing_id=housing.id,
            housing_name=housing.name,
            complex_name=housing.complex_name,
            sections=section_list,
        )
    )


@housing_router.post("/", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_housing(
    body: CreateHousingRequest,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[HousingSchema]:
    item = await service.housing_manager.create(body.model_dump())
    return DataResponseSchema[HousingSchema](data=HousingSchema.model_validate(item))


@housing_router.put("/{housing_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_housing(
    housing_id: UUID,
    body: UpdateHousingRequest,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[HousingSchema]:
    item = await service.housing_manager.update_by_id(housing_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Housing not found")
    return DataResponseSchema[HousingSchema](data=HousingSchema.model_validate(item))


@housing_router.delete("/{housing_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_housing(
    housing_id: UUID,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[dict]:
    await service.housing_manager.delete_by_id(housing_id)
    return DataResponseSchema[dict](data={"deleted": str(housing_id)})


# ── Sections ──────────────────────────────────────────────────────────────────


@housing_router.get("/{housing_id}/sections", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_sections(
    housing_id: UUID,
    service: HousingService = Depends(get_housing_service),
) -> ListDataResponseSchema[SectionSchema]:
    items = await service.section_manager.search(housing_id=housing_id, order_by=["section_number"])
    return ListDataResponseSchema[SectionSchema].create(
        list_data=[SectionSchema.model_validate(i) for i in items],
    )


@housing_router.post("/{housing_id}/sections", responses=get_responses(ResponseGroup.ALL_ERRORS), status_code=201)
@catch_all_exceptions
async def create_section(
    housing_id: UUID,
    body: CreateSectionRequest,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[SectionSchema]:
    data = body.model_dump()
    data["housing_id"] = housing_id
    item = await service.section_manager.create(data)
    return DataResponseSchema[SectionSchema](data=SectionSchema.model_validate(item))


@housing_router.put("/sections/{section_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_section(
    section_id: UUID,
    body: UpdateSectionRequest,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[SectionSchema]:
    item = await service.section_manager.update_by_id(section_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    return DataResponseSchema[SectionSchema](data=SectionSchema.model_validate(item))


@housing_router.delete("/sections/{section_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_section(
    section_id: UUID,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[dict]:
    await service.section_manager.delete_by_id(section_id)
    return DataResponseSchema[dict](data={"deleted": str(section_id)})


# ── Floors ────────────────────────────────────────────────────────────────────


@housing_router.get("/sections/{section_id}/floors", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def list_floors(
    section_id: UUID,
    service: HousingService = Depends(get_housing_service),
) -> ListDataResponseSchema[FloorSchema]:
    items = await service.floor_manager.search(section_id=section_id, order_by=["floor_number"])
    return ListDataResponseSchema[FloorSchema].create(
        list_data=[FloorSchema.model_validate(i) for i in items],
    )


@housing_router.post(
    "/sections/{section_id}/floors",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
    status_code=201,
)
@catch_all_exceptions
async def create_floor(
    section_id: UUID,
    body: CreateFloorRequest,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[FloorSchema]:
    data = body.model_dump()
    data["section_id"] = section_id
    item = await service.floor_manager.create(data)
    return DataResponseSchema[FloorSchema](data=FloorSchema.model_validate(item))


@housing_router.put("/floors/{floor_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def update_floor(
    floor_id: UUID,
    body: UpdateFloorRequest,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[FloorSchema]:
    item = await service.floor_manager.update_by_id(floor_id, body.model_dump(exclude_none=True))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Floor not found")
    return DataResponseSchema[FloorSchema](data=FloorSchema.model_validate(item))


@housing_router.delete("/floors/{floor_id}", responses=get_responses(ResponseGroup.ALL_ERRORS))
@catch_all_exceptions
async def delete_floor(
    floor_id: UUID,
    service: HousingService = Depends(get_housing_service),
) -> DataResponseSchema[dict]:
    await service.floor_manager.delete_by_id(floor_id)
    return DataResponseSchema[dict](data={"deleted": str(floor_id)})
