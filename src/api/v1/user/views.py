"""Who am I.

The frontend needs the user's name for the header and their groups to decide what to show. The
data is already in the request scope — the middleware fetched it from Raport while validating the
token — so this endpoint costs nothing and saves the browser a second base URL and a CORS setup.
"""

from fastapi import APIRouter, Request

from src.api.schemes import DataResponseSchema, ResponseGroup
from src.api.v1.user.schemes import CurrentUserSchema
from src.utils.helpers import catch_all_exceptions, get_responses

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.get(
    "/me",
    summary="The authenticated user",
    description="Returns the Raport profile of the caller. With AUTH_ENABLED=false there is "
    "nobody to describe, and `data` is null.",
    responses=get_responses(ResponseGroup.ALL_ERRORS),
)
@catch_all_exceptions
async def get_current_user(request: Request) -> DataResponseSchema[CurrentUserSchema | None]:
    user = request.scope.get("user")
    data = getattr(user, "data", None) if getattr(user, "is_authenticated", False) else None
    return DataResponseSchema[CurrentUserSchema | None](data=CurrentUserSchema.from_user(data) if data else None)
