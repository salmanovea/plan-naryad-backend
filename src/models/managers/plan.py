from typing import Optional
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.dbo.tables.contractor import Contractor
from src.models.dbo.tables.housing import Floor, Section
from src.models.dbo.tables.plan import PlanAdjustment, PlanItem
from src.models.dbo.tables.work import WorkType
from src.models.managers.common import BaseManager


class PlanItemManager(BaseManager[PlanItem]):
    """Data access for PlanItem entities."""

    entity = PlanItem

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def get_enriched_query(self) -> Select:
        """Base query eager-loading section/floor/work_type/contractor for labels."""
        return select(PlanItem).options(
            selectinload(PlanItem.section),
            selectinload(PlanItem.floor),
            selectinload(PlanItem.work_type),
            selectinload(PlanItem.contractor),
        )

    async def get_enriched_by_id(self, plan_item_id: UUID) -> Optional[PlanItem]:
        """Fetch a single plan item by id with its label relations eager-loaded."""
        query = self.get_enriched_query().where(PlanItem.id == plan_item_id)
        rows = await self.fetch(query)
        return rows[0] if rows else None


class PlanAdjustmentManager(BaseManager[PlanAdjustment]):
    """Data access for PlanAdjustment entities."""

    entity = PlanAdjustment

    def __init__(self, db: AsyncSession):
        super().__init__(db)
