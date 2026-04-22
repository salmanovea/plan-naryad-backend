import uuid

from sqlalchemy import Column, DateTime, Integer, func
from sqlalchemy.dialects.postgresql import UUID


class IDMixin:
    """Mixin that adds a UUID primary key to a model."""

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Mixin that adds `created_at` and `updated_at` audit columns."""

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
    )


class SortOrderMixin:
    """Mixin that adds a `sort_order` column for user-controlled ordering."""

    sort_order = Column(
        Integer,
        nullable=True,
        index=True,
    )
