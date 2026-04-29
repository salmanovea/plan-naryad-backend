from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.workforce import (
    ArticleBDR,
    WfArticleMapping,
    WfBudgetItem,
    WfBudgetPeriod,
    WfChallenge,
    WfChallengeItem,
    WfContractorAssignment,
    WfHeadcountFact,
    WfHeadcountPlan,
    WfMobilizationCheckpoint,
    WfMobilizationPlan,
    WfProject,
    WfProjectObject,
    WfViolation,
    WfWorkforceNorm,
)
from src.models.managers.common import BaseManager


class WfProjectManager(BaseManager[WfProject]):
    """Data access for WfProject entities."""

    entity = WfProject
    text_search_fields = {"name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfProjectObjectManager(BaseManager[WfProjectObject]):
    """Data access for WfProjectObject entities."""

    entity = WfProjectObject
    text_search_fields = {"name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfWorkforceNormManager(BaseManager[WfWorkforceNorm]):
    """Data access for WfWorkforceNorm entities."""

    entity = WfWorkforceNorm

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfBudgetPeriodManager(BaseManager[WfBudgetPeriod]):
    """Data access for WfBudgetPeriod entities."""

    entity = WfBudgetPeriod

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfBudgetItemManager(BaseManager[WfBudgetItem]):
    """Data access for WfBudgetItem entities."""

    entity = WfBudgetItem

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfHeadcountFactManager(BaseManager[WfHeadcountFact]):
    """Data access for WfHeadcountFact entities."""

    entity = WfHeadcountFact

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfHeadcountPlanManager(BaseManager[WfHeadcountPlan]):
    """Data access for WfHeadcountPlan entities."""

    entity = WfHeadcountPlan

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfContractorAssignmentManager(BaseManager[WfContractorAssignment]):
    """Data access for WfContractorAssignment entities."""

    entity = WfContractorAssignment

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfChallengeManager(BaseManager[WfChallenge]):
    """Data access for WfChallenge entities."""

    entity = WfChallenge

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfChallengeItemManager(BaseManager[WfChallengeItem]):
    """Data access for WfChallengeItem entities."""

    entity = WfChallengeItem

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfMobilizationPlanManager(BaseManager[WfMobilizationPlan]):
    """Data access for WfMobilizationPlan entities."""

    entity = WfMobilizationPlan

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfMobilizationCheckpointManager(BaseManager[WfMobilizationCheckpoint]):
    """Data access for WfMobilizationCheckpoint entities."""

    entity = WfMobilizationCheckpoint

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class ArticleBDRManager(BaseManager[ArticleBDR]):
    """Data access for ArticleBDR entities."""

    entity = ArticleBDR
    text_search_fields = {"code_1c": "ilike", "name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfArticleMappingManager(BaseManager[WfArticleMapping]):
    """Data access for WfArticleMapping entities (article ↔ work type links)."""

    entity = WfArticleMapping

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class WfViolationManager(BaseManager[WfViolation]):
    """Data access for WfViolation entities."""

    entity = WfViolation

    def __init__(self, db: AsyncSession):
        super().__init__(db)
