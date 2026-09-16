from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.settings import ActionLog, ContractorPositionLimit
from src.models.managers.common import BaseManager


class ContractorPositionLimitManager(BaseManager[ContractorPositionLimit]):
    """Data access for ContractorPositionLimit entities."""

    entity = ContractorPositionLimit

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ActionLogManager(BaseManager[ActionLog]):
    """Data access for ActionLog entities."""

    entity = ActionLog

    def __init__(self, db: AsyncSession):
        super().__init__(db)
