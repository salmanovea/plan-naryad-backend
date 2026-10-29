from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.settings import DEFAULT_TRANSFER_TIME, ActionLog, ContractorPositionLimit, PlanSettings
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


class PlanSettingsManager(BaseManager[PlanSettings]):
    """Data access for the single-row PlanSettings table."""

    entity = PlanSettings

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def get_transfer_time(self) -> time:
        """The configured transfer time; the default when the row is missing."""
        rows = await self.search()
        return rows[0].transfer_time if rows else DEFAULT_TRANSFER_TIME
