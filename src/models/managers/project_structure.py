from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.project_structure import ConstructionObject, Project, Queue
from src.models.managers.common import BaseManager


class ProjectManager(BaseManager[Project]):
    """Data access for Project entities."""

    entity = Project
    text_search_fields = {"name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class QueueManager(BaseManager[Queue]):
    """Data access for Queue entities."""

    entity = Queue
    text_search_fields = {"name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ConstructionObjectManager(BaseManager[ConstructionObject]):
    """Data access for ConstructionObject entities."""

    entity = ConstructionObject
    text_search_fields = {"name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)
