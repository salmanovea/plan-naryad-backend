"""Operational settings and the action journal."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.mixins import IDMixin
from src.models.dbo.base_model import Base

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor
    from src.models.dbo.tables.work import Work


class ContractorFloorLimit(IDMixin, Base):
    """How many floors of one work may land on one contractor in a single day plan.

    Resolution cascade, most specific first:
      1. row matching both contractor and work
      2. row for the work with `contractor_id IS NULL`
      3. `DEFAULT_FLOOR_LIMIT` from settings
    """

    __tablename__ = "contractor_floor_limits"

    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("contractors.id", name="fk_contractor_floor_limits_contractor_id"),
        index=True,
    )
    work_id: Mapped[UUID] = mapped_column(
        ForeignKey("works.id", name="fk_contractor_floor_limits_work_id"),
        nullable=False,
        index=True,
    )
    floors_limit: Mapped[int] = mapped_column(Integer, nullable=False)

    contractor: Mapped[Optional["Contractor"]] = relationship()  # type: ignore[name-defined]
    work: Mapped["Work"] = relationship()  # type: ignore[name-defined]

    __table_args__ = (
        Index(
            "uq_contractor_floor_limits_key",
            "contractor_id",
            "work_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )


class ActionType(str, Enum):
    """Actions the spec requires to be journalled."""

    PLAN_GENERATE = "plan_generate"
    PLAN_ITEM_CREATE = "plan_item_create"
    PLAN_ITEM_DELETE = "plan_item_delete"
    PLAN_ITEM_CONFIRM = "plan_item_confirm"


class ActionLog(IDMixin, Base):
    """Who did what and when.

    `actor` holds the caller's Keycloak id (`fsk_id`/`sub` as a string), «system» for scheduler
    jobs and unauthenticated local runs, or a client id for machine callers. Never a name or a
    username — audit rows are kept forever, and a person's name in them is personal data.
    """

    __tablename__ = "action_logs"

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[UUID]] = mapped_column(Uuid(as_uuid=True), index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), index=True)
