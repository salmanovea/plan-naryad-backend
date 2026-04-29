from datetime import datetime
from enum import Enum
from uuid import UUID
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    TypeVar,
    Type,
    TypedDict,
)


from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseResponse(BaseModel):
    """
    All responses must be inherited from this class,
    except ErrorResponse
    """

    code: str = "200"
    message: str = "Response"


class ErrorResponse(BaseResponse):
    code: str = "400"
    message: str = "Response Error"


class Response200Schema(BaseResponse):
    code: str = "200"
    message: str = Field(
        default="Success: The request has been successfully processed and the response contains the requested data.",
        examples=["Success: Data retrieved successfully."],
    )


class Response201Schema(BaseResponse):
    code: str = "201"
    message: str = Field(
        default="Created: The request has been fulfilled and resulted in a new resource being created.",
        examples=["Created: New resource successfully created."],
    )


class Response400Schema(ErrorResponse):
    code: str = "400"
    message: str = Field(
        default="Bad Request: The server could not understand the request due to invalid syntax.",
        examples=[
            "Bad Request: Missing required parameters.",
            "Bad Request: Invalid data format.",
        ],
    )
    details: list | None = Field(default=None)


class Response401Schema(ErrorResponse):
    code: str = "401"
    message: str = Field(
        default="Unauthorized: The request requires user authentication or the provided authentication is invalid.",
        examples=[
            "Unauthorized: Invalid or expired token.",
            "Unauthorized: No authentication credentials provided.",
        ],
    )


class Response403Schema(ErrorResponse):
    code: str = "403"
    message: str = Field(
        default="Forbidden: The server understood the request, but it refuses to authorize it.",
        examples=["Forbidden: You do not have permission to access this resource."],
    )


class Response404Schema(ErrorResponse):
    code: str = "404"
    message: str = Field(
        default="Not Found: The requested resource could not be found on the server.",
        examples=[
            "Not Found: The requested resource does not exist.",
            "Not Found: Resource with the specified ID not found.",
        ],
    )


class Response413Schema(ErrorResponse):
    code: str = "413"
    message: str = Field(
        default="Payload Too Large: The request is larger than the server is willing or able to process.",
        examples=[
            "Payload Too Large: The uploaded file exceeds the maximum allowed size.",
        ],
    )


class Response422Schema(ErrorResponse):
    code: str = "422"
    message: str = Field(
        default="Unprocessable Entity: The server understands the content type of the request entity, but was unable "
        "to process the contained instructions.",
        examples=["Unprocessable Entity: The provided data is invalid."],
    )
    details: list | None = Field(default=None)


class Response429Schema(ErrorResponse):
    code: str = "429"
    message: str = Field(
        default="Too Many Requests: The user has sent too many requests in a given amount of time.",
        examples=["Too Many Requests: Rate limit exceeded."],
    )


class Response500Schema(ErrorResponse):
    code: str = "500"
    message: str = Field(
        default="Internal Server Error: The server encountered an unexpected condition that prevented it from "
        "fulfilling the request.",
        examples=["Internal Server Error: Unexpected error occurred."],
    )


class DebugResponse500Schema(ErrorResponse):
    code: str = "500"
    message: str
    trace: list


class Response503Schema(ErrorResponse):
    code: str = "503"
    message: str = Field(
        default="Service Unavailable: The server is currently unable to handle the request due to temporary "
        "overloading or maintenance of the server.",
        examples=["Service Unavailable: The server is under maintenance."],
    )


class PaginationSchema(BaseModel):
    """
    Pagination data schema.

    Attributes:
        total_items: total number of elements
        page: current page
        items_per_page: number of items per page
        next_page: number of the next page
        prev_page: number of the previous page
        total_pages: number of total pages
    """

    total_items: int = Field(..., description="Total number of elements (must be positive)")
    page: int = Field(..., description="Current page (must be at least 1)")
    items_per_page: int = Field(..., description="Number of items per page (must be positive)")
    next_page: int | None = Field(None, description="Number of the next page (can be None)")
    prev_page: int | None = Field(None, description="Number of the previous page (can be None)")
    total_pages: int = Field(..., description="Number of total pages (must be positive)")


class PaginationParams(BaseModel):
    page: int = Field(..., ge=1)
    per_page: int = Field(..., ge=1)


class SortOrderOptions(str, Enum):
    asc = "asc"
    desc = "desc"


class BaseSortOptions(str, Enum):
    @classmethod
    def default(cls) -> str:
        return next(iter(cls))


class NamedSortOptions(BaseSortOptions):
    name = "name"
    id = "id"


class SortParams(BaseModel):
    """
    Sorting parameters.

    Attributes:
        sort_by: fields by which sorting is performed
        order_by: sort orders corresponding to fields (asc or desc)
    """

    sort_by: Optional[List[str]] = Field(None, description="The fields by which the sorting is performed")
    order_by: Optional[List[str]] = Field(None, description="Sort orders corresponding to fields (asc or desc)")


class OrderParams(BaseModel):
    order_by: Optional[List[str]] = Field(Query(None, description="Order by entity fields"))


class DataResponseSchema(Response200Schema, Generic[T]):
    data: T


class ListDataResponseSchema(Response200Schema, Generic[T]):
    data: List[T]
    pagination: PaginationSchema | None = None

    @classmethod
    def create(
        cls,
        list_data: List[Dict[str, Any]],
        pagination: PaginationParams | None = None,
        total: int | None = None,
        message: str = "Success",
        additional_data: dict | None = None,
    ):
        from src.utils.helpers import get_pagination_info

        if not additional_data:
            additional_data = dict()

        if pagination is None and total is None:
            return cls(data=list_data, message=message)

        return cls(
            data=list_data,
            pagination=get_pagination_info(pagination, total),
            message=message,
        )


class NamedEntitySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    name: Optional[str] = None


class IDMixinSchema(BaseModel):
    id: UUID


class IdOptionalMixin(BaseModel):
    id: Optional[UUID] = None


class HousingBaseFilters(BaseModel):
    housing_id: Optional[UUID] = Query(None, description="Filter by housing id")
    housing_id__in: Optional[List[UUID]] = Field(Query(None, description="Filter by housing id list"))


class SectionBaseFilters(BaseModel):
    section_id: Optional[UUID] = Query(None, description="Filter by section id")
    section_id__in: Optional[List[UUID]] = Field(Query(None, description="Filter by section id list"))


class FloorBaseFilters(BaseModel):
    floor_id: Optional[UUID] = Query(None, description="Filter by floor id")
    floor_id__in: Optional[List[UUID]] = Field(Query(None, description="Filter by floor id list"))


class ContractorBaseFilters(BaseModel):
    contractor_id: Optional[UUID] = Query(None, description="Filter by contractor id")
    contractor_id__in: Optional[List[UUID]] = Field(Query(None, description="Filter by contractor id list"))


class WorkGroupBaseFilters(BaseModel):
    work_group_id: Optional[UUID] = Query(None, description="Filter by work_group id")
    work_group_id__in: Optional[List[UUID]] = Field(Query(None, description="Filter by work_group id list"))


class WorkTypeBaseFilters(BaseModel):
    work_type_id: Optional[UUID] = Query(None, description="Filter by work_type id")
    work_type_id__in: Optional[List[UUID]] = Field(Query(None, description="Filter by work_type id list"))


class TimestampBaseFilters(BaseModel):
    created_at__gte: Optional[datetime] = Query(None, description="Filter by creation date from (inclusive)")
    created_at__lte: Optional[datetime] = Query(None, description="Filter by creation date to (inclusive)")
    updated_at__gte: Optional[datetime] = Query(None, description="Filter by update date from (inclusive)")
    updated_at__lte: Optional[datetime] = Query(None, description="Filter by update date to (inclusive)")


class ResponseGroup(str, Enum):
    SUCCESS = "SUCCESS"
    AUTH_ERRORS = "AUTH_ERRORS"
    CLIENT_ERRORS = "CLIENT_ERRORS"
    SERVER_ERRORS = "SERVER_ERRORS"
    VALIDATION_ERRORS = "VALIDATION_ERRORS"
    RATE_LIMIT_ERRORS = "RATE_LIMIT_ERRORS"
    ALL_ERRORS = "ALL_ERRORS"
    ALL = "ALL"


class ResponseSchemaInfo(TypedDict):
    model: Type[BaseModel]
    description: str


RESPONSE_SCHEMAS: dict[str, ResponseSchemaInfo] = {
    "200": {"model": Response200Schema, "description": "Successful response"},
    "201": {"model": Response201Schema, "description": "Resource created successfully"},
    "400": {"model": Response400Schema, "description": "Bad Request"},
    "401": {"model": Response401Schema, "description": "Unauthorized"},
    "403": {"model": Response403Schema, "description": "Forbidden"},
    "404": {"model": Response404Schema, "description": "Not Found"},
    "413": {"model": Response413Schema, "description": "Payload Too Large"},
    "422": {"model": Response422Schema, "description": "Unprocessable Entity"},
    "429": {"model": Response429Schema, "description": "Too Many Requests"},
    "500": {"model": Response500Schema, "description": "Internal Server Error"},
    "503": {"model": Response503Schema, "description": "Service Unavailable"},
}


RESPONSE_GROUPS: dict[ResponseGroup, list[str]] = {
    ResponseGroup.SUCCESS: ["200", "201"],
    ResponseGroup.AUTH_ERRORS: ["401", "403"],
    ResponseGroup.CLIENT_ERRORS: ["400", "404", "422"],
    ResponseGroup.SERVER_ERRORS: ["500", "503"],
    ResponseGroup.VALIDATION_ERRORS: ["422"],
    ResponseGroup.RATE_LIMIT_ERRORS: ["429"],
    ResponseGroup.ALL_ERRORS: ["400", "401", "403", "404", "413", "422", "429", "500", "503"],
    ResponseGroup.ALL: ["200", "201", "400", "401", "403", "404", "413", "422", "429", "500", "503"],
}


class DeleteMultipleRequestSchema(BaseModel):
    ids: list[UUID]
