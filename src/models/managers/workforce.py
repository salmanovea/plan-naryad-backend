from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.dbo.tables.project_structure import ConstructionObject
from src.models.dbo.tables.workforce import (
    ArticleBDR,
    ArticleBDRWork,
    BudgetItem,
    BudgetPeriod,
    Challenge,
    ChallengeItem,
    CheckpointStatus,
    ContractorAssignment,
    HeadcountFact,
    HeadcountNorm,
    HeadcountPlan,
    MobilizationCheckpoint,
    MobilizationPlan,
    Violation,
)
from src.models.managers.access import IdQuery
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

    async def latest(self, project_id: UUID, period_month: date | None = None) -> BudgetPeriod | None:
        """Latest budget period of an already authorized project."""
        query = select(BudgetPeriod).where(BudgetPeriod.project_id == project_id)
        if period_month is not None:
            query = query.where(BudgetPeriod.period_month == period_month)
        rows = await self.fetch(query.order_by(BudgetPeriod.period_month.desc()).limit(1))
        return rows[0] if rows else None


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

    async def averages(
        self,
        since: date,
        group_by: tuple[str, ...],
        allowed_ids: IdQuery | None,
        project_id: UUID | None = None,
        construction_object_id: UUID | None = None,
    ) -> list[Row[Any]]:
        """Aggregate authorized facts before grouping by the requested domain dimensions."""
        columns = [getattr(HeadcountFact, field) for field in group_by]
        query = select(*columns, func.avg(HeadcountFact.count).label("avg")).group_by(*columns)
        query = self.apply_filters(query, fact_date__gte=since, id__in=allowed_ids)
        if project_id is not None:
            query = query.where(HeadcountFact.project_id == project_id)
        if construction_object_id is not None:
            query = query.where(HeadcountFact.construction_object_id == construction_object_id)
        return await self.fetch(query, with_scalars=False)

    async def contractor_average(self, contractor_id: UUID, since: date, allowed_ids: IdQuery | None) -> float | None:
        """Average only the contractor's facts in the operation's accessible projects."""
        query = select(func.avg(HeadcountFact.count)).where(HeadcountFact.contractor_id == contractor_id)
        query = self.apply_filters(query, fact_date__gte=since, id__in=allowed_ids)
        return await self.fetch_val(query)


class HeadcountPlanManager(BaseManager[HeadcountPlan]):
    """Data access for HeadcountPlan entities."""

    entity = HeadcountPlan

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def planned_rows(
        self,
        period_month: date,
        allowed_ids: IdQuery | None,
        project_id: UUID | None = None,
        construction_object_id: UUID | None = None,
        include_contractor: bool = False,
    ) -> list[Row[Any]]:
        """Read authorized plans for a project or construction object."""
        columns = [HeadcountPlan.work_id, HeadcountPlan.planned_count]
        if include_contractor:
            columns.insert(0, HeadcountPlan.contractor_id)
        query = select(*columns).where(HeadcountPlan.period_month == period_month)
        if project_id is not None:
            query = query.where(HeadcountPlan.project_id == project_id)
        if construction_object_id is not None:
            query = query.where(HeadcountPlan.construction_object_id == construction_object_id)
        query = self.apply_filters(query, id__in=allowed_ids)
        return await self.fetch(query, with_scalars=False)

    async def contractor_total(self, contractor_id: UUID, since: date, allowed_ids: IdQuery | None) -> int | None:
        """Sum only authorized plans for the contractor rating."""
        query = select(func.sum(HeadcountPlan.planned_count)).where(HeadcountPlan.contractor_id == contractor_id)
        query = self.apply_filters(query, period_month__gte=since, id__in=allowed_ids)
        return await self.fetch_val(query)


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

    def get_base_query(self) -> Select[tuple[Challenge]]:
        """Load challenge lines before the HTTP layer serializes them."""
        return select(Challenge).options(selectinload(Challenge.items))

    async def get_with_items(self, challenge_id: UUID) -> Challenge:
        """Reload a newly created challenge with its lines for serialization."""
        query = select(Challenge).where(Challenge.id == challenge_id).options(selectinload(Challenge.items))
        result = await self.db.execute(query)
        return result.scalar_one()


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

    async def missed_count(self, contractor_id: UUID, allowed_ids: IdQuery | None) -> int:
        """Count missed checkpoints within the caller's project assignments."""
        query = (
            select(func.count(MobilizationCheckpoint.id))
            .join(MobilizationPlan, MobilizationCheckpoint.mobilization_plan_id == MobilizationPlan.id)
            .join(ChallengeItem, MobilizationPlan.challenge_item_id == ChallengeItem.id)
            .join(Challenge, ChallengeItem.challenge_id == Challenge.id)
            .join(ConstructionObject, Challenge.construction_object_id == ConstructionObject.id)
            .join(ContractorAssignment, ContractorAssignment.construction_object_id == ConstructionObject.id)
            .where(
                ContractorAssignment.contractor_id == contractor_id,
                MobilizationCheckpoint.status == CheckpointStatus.MISSED,
            )
        )
        query = self.apply_filters(query, id__in=allowed_ids)
        return await self.fetch_val(query) or 0

    async def pending_for_challenge(
        self, challenge_id: UUID, today: date, allowed_ids: IdQuery | None
    ) -> list[MobilizationCheckpoint]:
        """Due checkpoints of an explicitly authorized challenge."""
        query = (
            select(MobilizationCheckpoint)
            .join(MobilizationPlan, MobilizationCheckpoint.mobilization_plan_id == MobilizationPlan.id)
            .join(ChallengeItem, MobilizationPlan.challenge_item_id == ChallengeItem.id)
            .where(
                ChallengeItem.challenge_id == challenge_id,
                MobilizationCheckpoint.check_date <= today,
                MobilizationCheckpoint.status == CheckpointStatus.PENDING,
            )
        )
        return await self.fetch(self.apply_filters(query, id__in=allowed_ids))


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
