import math
from functools import wraps
from typing import (
    Type,
    List,
    Union,
    Callable,
    Awaitable,
    TypeVar,
    ParamSpec,
    cast as t_cast,
)

from fastapi import HTTPException, Query, status
from fastapi.exceptions import RequestValidationError

from pydantic import ValidationError, BaseModel

from sqlalchemy import Enum as SQLAlchemyEnum, Select, String, cast

from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.schemes import (
    ResponseGroup,
    RESPONSE_GROUPS,
    RESPONSE_SCHEMAS,
    ResponseSchemaInfo,
    PaginationParams,
)
from src.config.logger import LoggerProvider

P = ParamSpec("P")
R = TypeVar("R")
log = LoggerProvider().get_logger(__name__)


def get_responses(
    groups: Union[List[ResponseGroup], ResponseGroup],
) -> dict[int | str, ResponseSchemaInfo]:
    """
    Returns a dictionary of OpenAPI-compatible response schemas based on one or more response groups.

    Args:
        groups: A single ResponseGroup or a list of ResponseGroups (e.g., AUTH_ERRORS, CLIENT_ERRORS).

    Returns:
        A dictionary mapping HTTP status codes (as strings) to their corresponding response schema dicts,
        suitable for FastAPI's 'responses' parameter.
    """
    if isinstance(groups, ResponseGroup):
        groups = [groups]

    response_codes = set()
    for group in groups:
        response_codes.update(RESPONSE_GROUPS[group])

    return {code: RESPONSE_SCHEMAS[code] for code in response_codes if code in RESPONSE_SCHEMAS}


def catch_all_exceptions(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[JSONResponse | R]]:
    """
    Universal exception handler that uses RESPONSE_GROUPS[ALL_ERRORS]
    to provide consistent error response schemas across all known errors.
    """

    HANDLED_ERROR_CODES = set(RESPONSE_GROUPS[ResponseGroup.ALL_ERRORS])

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> JSONResponse | R:
        schema_cls: Type[BaseModel]

        try:
            return await func(*args, **kwargs)

        except RequestValidationError as e:
            schema_cls = RESPONSE_SCHEMAS["400"]["model"]
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=schema_cls(
                    code="400",
                    message="Bad Request: Invalid input.",
                    details=e.errors(),
                ).model_dump(),
            )

        except ValidationError as e:
            schema_cls = RESPONSE_SCHEMAS["422"]["model"]
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=schema_cls(
                    code="422",
                    message="Unprocessable Entity: Validation failed.",
                    details=e.errors(),
                ).model_dump(),
            )

        except (HTTPException, StarletteHTTPException) as e:
            status_code_str = str(e.status_code)
            message = getattr(e, "detail", str(e))

            if status_code_str in HANDLED_ERROR_CODES:
                schema_cls = RESPONSE_SCHEMAS[status_code_str]["model"]
                content = schema_cls(message=str(e.detail)).model_dump()
                return JSONResponse(
                    status_code=int(status_code_str),
                    content=content,
                )
            else:
                log.warning(f"Unexpected HTTPException {status_code_str}: {message}")
                return JSONResponse(
                    status_code=int(status_code_str),
                    content={"code": status_code_str, "message": message},
                )

        except ClientDisconnect:
            log.warning("Client disconnected during request.")
            return JSONResponse(
                status_code=499,
                content={"code": "499", "message": "Client Closed Request: Client disconnected."},
            )

        except Exception:
            log.exception("Unhandled exception in endpoint")
            schema_cls = RESPONSE_SCHEMAS["500"]["model"]
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=schema_cls(
                    code="500",
                    message="Internal Server Error: Unexpected error occurred.",
                ).model_dump(),
            )

    return t_cast(Callable[P, Awaitable[JSONResponse | R]], wrapper)


def pagination_params(
    page: int = Query(1, ge=1, description="Page number (1 or greater)"),
    per_page: int = Query(1000, ge=1, le=100000, description="Items per page (1..100000)"),
) -> PaginationParams:
    """Validate and build PaginationParams from query string.

    Default per_page=1000 fits current reference collections (housings:506,
    projects:41, works:377/103). Contractors (~47k) explicitly request
    per_page=100000 from the frontend until server-side paging is wired up.
    """
    if page < 1 or per_page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page and per_page must be greater than 0",
        )
    return PaginationParams(page=page, per_page=per_page)


def get_paginated_query(query: Select, pagination: PaginationParams) -> Select:
    """Apply LIMIT/OFFSET to a SQLAlchemy Select based on PaginationParams."""
    return query.limit(pagination.per_page).offset((pagination.page - 1) * pagination.per_page)


def safe_ilike(col, val: str):
    """
    ILIKE that works for both string and Enum columns by casting Enum values
    to String before applying the pattern.
    """
    if isinstance(col.type, SQLAlchemyEnum):
        return cast(col, String).ilike(f"%{val}%")
    return col.ilike(f"%{val}%")


def get_pagination_info(pagination: PaginationParams | None, total: int | None) -> dict[str, int | bool | None]:
    """
    Generate pagination info based on the current page, items per page, and total items.

    Args:
        pagination: The pagination parameters.
        total: The total number of items.

    Returns:
        A dictionary containing pagination info.
    """
    if pagination is None or total is None:
        return {
            "total_items": total,
            "page": None,
            "items_per_page": None,
            "next_page": None,
            "prev_page": None,
            "total_pages": None,
        }
    is_last_page = pagination.page * pagination.per_page >= total
    total_pages = math.ceil(total / pagination.per_page) if pagination.per_page else 0
    return {
        "total_items": total,
        "page": pagination.page,
        "items_per_page": pagination.per_page,
        "next_page": pagination.page + 1 if not is_last_page else None,
        "prev_page": pagination.page - 1 if pagination.page > 1 else None,
        "total_pages": total_pages,
    }
