from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    if TYPE_CHECKING:
        # Every concrete model carries a primary-key `id` (via IDMixin). Declaring
        # it here — type-check time only — lets generic managers (BaseManager[T])
        # reference `self.entity.id` without mypy complaining. Not mapped at runtime.
        id: Any
