from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.work import TechSequenceItem, WorkGroup, WorkType
from src.models.managers.common import BaseManager


class WorkGroupManager(BaseManager[WorkGroup]):
    """Data access for WorkGroup entities."""

    entity = WorkGroup
    text_search_fields = {"name": "ilike", "code": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WorkTypeManager(BaseManager[WorkType]):
    """Data access for WorkType entities."""

    entity = WorkType
    text_search_fields = {"name": "ilike", "code": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class TechSequenceItemManager(BaseManager[TechSequenceItem]):
    """Data access for TechSequenceItem entities."""

    entity = TechSequenceItem

    def __init__(self, db: AsyncSession):
        super().__init__(db)
