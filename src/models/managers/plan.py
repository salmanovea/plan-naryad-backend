from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.plan import PlanAdjustment, PlanItem
from src.models.managers.common import BaseManager


class PlanItemManager(BaseManager[PlanItem]):
    """Data access for PlanItem entities."""

    entity = PlanItem

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class PlanAdjustmentManager(BaseManager[PlanAdjustment]):
    """Data access for PlanAdjustment entities."""

    entity = PlanAdjustment

    def __init__(self, db: AsyncSession):
        super().__init__(db)
