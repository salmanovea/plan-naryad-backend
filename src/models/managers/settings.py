from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.settings import ActionLog, ContractorFloorLimit
from src.models.managers.common import BaseManager


class ContractorFloorLimitManager(BaseManager[ContractorFloorLimit]):
    """Data access for ContractorFloorLimit entities."""

    entity = ContractorFloorLimit

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ActionLogManager(BaseManager[ActionLog]):
    """Data access for ActionLog entities."""

    entity = ActionLog

    def __init__(self, db: AsyncSession):
        super().__init__(db)
