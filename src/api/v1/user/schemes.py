from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from src.api.schemes import NamedEntitySchema


class CurrentUserSchema(BaseModel):
    """The authenticated user, as Raport describes them."""

    id: Optional[UUID] = None
    shown_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    email: Optional[str] = None
    is_external: Optional[bool] = None
    is_admin: Optional[bool] = None
    groups: list[str] = []
    projects: list[NamedEntitySchema] = []
    contractors: list[NamedEntitySchema] = []

    @classmethod
    def from_user(cls, data: dict[str, Any]) -> "CurrentUserSchema":
        return cls.model_validate({key: value for key, value in data.items() if key in cls.model_fields})
