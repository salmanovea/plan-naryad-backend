from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.contract import Contract
from src.models.managers.common import BaseManager


class ContractManager(BaseManager[Contract]):
    """Data access for Contract entities."""

    entity = Contract
    text_search_fields = {"name": "ilike", "subject": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)
