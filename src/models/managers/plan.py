from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def get_daily_plan_items(self, target_date: date, housing_id: UUID) -> list[PlanItem]:
        """Fetch plan items for a day with joined work/section/floor/contractor labels."""
        stmt = (
            select(
                PlanItem,
                WorkType.name.label("work_name"),
                Section.name.label("section_name"),
                Floor.floor_number.label("floor_number"),
                Contractor.name.label("contractor_name"),
            )
            .join(WorkType, PlanItem.work_type_id == WorkType.id)
            .join(Section, PlanItem.section_id == Section.id)
            .join(Floor, PlanItem.floor_id == Floor.id)
            .join(Contractor, PlanItem.contractor_id == Contractor.id)
            .where(PlanItem.date == target_date)
            .where(PlanItem.housing_id == housing_id)
        )
        result = await self.db.execute(stmt)
        items: list[PlanItem] = []
        for plan_item, work_name, section_name, floor_number, contractor_name in result.all():
            plan_item.work_name = work_name
            plan_item.section_name = section_name
            plan_item.floor_number = str(floor_number) if floor_number is not None else None
            plan_item.contractor_name = contractor_name
            items.append(plan_item)
        return items


class PlanAdjustmentManager(BaseManager[PlanAdjustment]):
    """Data access for PlanAdjustment entities."""

    entity = PlanAdjustment

    def __init__(self, db: AsyncSession):
        super().__init__(db)
