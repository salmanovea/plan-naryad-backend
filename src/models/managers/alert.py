from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.alert import Alert
from src.models.managers.common import BaseManager


class AlertManager(BaseManager[Alert]):
    """Data access for Alert entities."""

    entity = Alert
    text_search_fields = {"message": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)
