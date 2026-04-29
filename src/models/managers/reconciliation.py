from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.reconciliation import DailySummary, ReconciliationResult
from src.models.managers.common import BaseManager


class ReconciliationResultManager(BaseManager[ReconciliationResult]):
    """Data access for ReconciliationResult entities."""

    entity = ReconciliationResult

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class DailySummaryManager(BaseManager[DailySummary]):
    """Data access for DailySummary entities."""

    entity = DailySummary

    def __init__(self, db: AsyncSession):
        super().__init__(db)
