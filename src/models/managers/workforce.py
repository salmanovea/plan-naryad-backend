from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.workforce import (
    ArticleBDR,
    ArticleBDRWork,
    BudgetItem,
    BudgetPeriod,
    Challenge,
    ChallengeItem,
    ContractorAssignment,
    HeadcountFact,
    HeadcountNorm,
    HeadcountPlan,
    MobilizationCheckpoint,
    MobilizationPlan,
    Violation,
)
from src.models.managers.common import BaseManager


class HeadcountNormManager(BaseManager[HeadcountNorm]):
    """Data access for HeadcountNorm entities."""

    entity = HeadcountNorm

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class BudgetPeriodManager(BaseManager[BudgetPeriod]):
    """Data access for BudgetPeriod entities."""

    entity = BudgetPeriod

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class BudgetItemManager(BaseManager[BudgetItem]):
    """Data access for BudgetItem entities."""

    entity = BudgetItem

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class HeadcountFactManager(BaseManager[HeadcountFact]):
    """Data access for HeadcountFact entities."""

    entity = HeadcountFact

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class HeadcountPlanManager(BaseManager[HeadcountPlan]):
    """Data access for HeadcountPlan entities."""

    entity = HeadcountPlan

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ContractorAssignmentManager(BaseManager[ContractorAssignment]):
    """Data access for workforce ContractorAssignment entities (object × work)."""

    entity = ContractorAssignment

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ChallengeManager(BaseManager[Challenge]):
    """Data access for Challenge entities."""

    entity = Challenge

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ChallengeItemManager(BaseManager[ChallengeItem]):
    """Data access for ChallengeItem entities."""

    entity = ChallengeItem

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class MobilizationPlanManager(BaseManager[MobilizationPlan]):
    """Data access for MobilizationPlan entities."""

    entity = MobilizationPlan

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class MobilizationCheckpointManager(BaseManager[MobilizationCheckpoint]):
    """Data access for MobilizationCheckpoint entities."""

    entity = MobilizationCheckpoint

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ArticleBDRManager(BaseManager[ArticleBDR]):
    """Data access for ArticleBDR entities."""

    entity = ArticleBDR
    text_search_fields = {"code_1c": "ilike", "name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ArticleBDRWorkManager(BaseManager[ArticleBDRWork]):
    """Data access for ArticleBDRWork entities (article ↔ work links)."""

    entity = ArticleBDRWork

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ViolationManager(BaseManager[Violation]):
    """Data access for Violation entities."""

    entity = Violation

    def __init__(self, db: AsyncSession):
        super().__init__(db)
