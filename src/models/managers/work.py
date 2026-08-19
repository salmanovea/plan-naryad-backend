from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.dbo.tables.work import TechSequenceItem, Work, WorkGroup, WorkSet, WorkType
from src.models.managers.common import BaseManager


class WorkSetManager(BaseManager[WorkSet]):
    """Data access for WorkSet entities («Этап»)."""

    entity = WorkSet
    text_search_fields = {"name": "ilike", "code": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WorkGroupManager(BaseManager[WorkGroup]):
    """Data access for WorkGroup entities («Комплекс»)."""

    entity = WorkGroup
    text_search_fields = {"name": "ilike", "code": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WorkTypeManager(BaseManager[WorkType]):
    """Data access for WorkType entities («Вид работ»)."""

    entity = WorkType
    text_search_fields = {"name": "ilike", "code": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WorkManager(BaseManager[Work]):
    """Data access for Work entities («Работа») — the operational leaf."""

    entity = Work
    text_search_fields = {"name": "ilike", "code": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def get_enriched_by_ids(self, work_ids: list[UUID]) -> list[Work]:
        """Works with their catalogue chain loaded — «Этап → Комплекс → Вид → Работа».

        The chain feeds the work filter trees; lazy-loading it during serialisation would
        blow up with MissingGreenlet outside the async context.
        """
        if not work_ids:
            return []
        query = (
            select(Work)
            .where(Work.id.in_(work_ids))
            .options(selectinload(Work.work_type).selectinload(WorkType.work_group).selectinload(WorkGroup.work_set))
        )
        return list(await self.fetch(query))


class TechSequenceItemManager(BaseManager[TechSequenceItem]):
    """Data access for TechSequenceItem entities."""

    entity = TechSequenceItem

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def get_enriched_query(self) -> Select:
        """Base query eager-loading `work`.

        `TechSequenceItemSchema` serialises the nested work, and a lazy load during
        Pydantic validation blows up with MissingGreenlet outside the async context.
        """
        return select(TechSequenceItem).options(selectinload(TechSequenceItem.work))
