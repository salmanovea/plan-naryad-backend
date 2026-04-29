from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.fact import WorkFact
from src.models.managers.common import BaseManager


class WorkFactManager(BaseManager[WorkFact]):
    """Data access for WorkFact entities."""

    entity = WorkFact

    def __init__(self, db: AsyncSession):
        super().__init__(db)
