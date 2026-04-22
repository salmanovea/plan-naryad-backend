from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.contractor import Contractor, ContractorAssignment
from src.models.managers.common import BaseManager


class ContractorManager(BaseManager[Contractor]):
    """Data access for Contractor entities."""

    entity = Contractor
    text_search_fields = {"name": "ilike", "short_name": "ilike", "inn": "ilike", "description": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ContractorAssignmentManager(BaseManager[ContractorAssignment]):
    """Data access for ContractorAssignment entities."""

    entity = ContractorAssignment

    def __init__(self, db: AsyncSession):
        super().__init__(db)
