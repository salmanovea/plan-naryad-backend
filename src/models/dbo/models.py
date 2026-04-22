from sqlalchemy.orm import DeclarativeBase

from src.models.dbo.mixins import IDMixin, TimestampMixin, SortOrderMixin  # noqa: F401


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass
