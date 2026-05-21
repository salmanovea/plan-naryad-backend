from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemes import PaginationParams
from src.models.dbo.tables.contractor import Contractor
from src.models.dbo.tables.housing import Floor, Housing, Section
from src.models.dbo.tables.reconciliation import DailySummary, ReconciliationResult
from src.models.dbo.tables.work import WorkType
from src.models.managers.common import BaseManager
from src.utils.helpers import get_paginated_query


class ReconciliationResultManager(BaseManager[ReconciliationResult]):
    """Data access for ReconciliationResult entities."""

    entity = ReconciliationResult

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def _select_with_names(self):
        return (
            select(
                ReconciliationResult,
                Housing.name.label("housing_name"),
                Section.name.label("section_name"),
                Floor.name.label("floor_name"),
                WorkType.name.label("work_name"),
                Contractor.name.label("contractor_name"),
            )
            .join(Housing, ReconciliationResult.housing_id == Housing.id)
            .join(Section, ReconciliationResult.section_id == Section.id)
            .join(Floor, ReconciliationResult.floor_id == Floor.id)
            .join(WorkType, ReconciliationResult.work_type_id == WorkType.id)
            .join(Contractor, ReconciliationResult.contractor_id == Contractor.id)
        )

    @staticmethod
    def _attach_names(result: ReconciliationResult, names: tuple) -> ReconciliationResult:
        housing_name, section_name, floor_name, work_name, contractor_name = names
        result.housing_name = housing_name
        result.section_name = section_name
        result.floor_name = floor_name
        result.work_name = work_name
        result.contractor_name = contractor_name
        return result

    async def search_with_names(
        self,
        order_by: Optional[list[str]] = None,
        pagination: Optional[PaginationParams] = None,
        **filters,
    ) -> list[ReconciliationResult]:
        """Search results and attach joined housing/section/floor/work/contractor names."""
        stmt = self._select_with_names()
        stmt = self.apply_filters(stmt, **filters)
        if order_by:
            stmt = self.apply_ordering(stmt, order_by)
        if pagination:
            stmt = get_paginated_query(stmt, pagination)

        rows = (await self.db.execute(stmt)).all()
        return [self._attach_names(row[0], row[1:]) for row in rows]

    async def get_by_id_with_names(self, result_id: UUID) -> Optional[ReconciliationResult]:
        """Fetch a single reconciliation result enriched with joined names."""
        stmt = self._select_with_names().where(ReconciliationResult.id == result_id)
        row = (await self.db.execute(stmt)).first()
        if row is None:
            return None
        return self._attach_names(row[0], row[1:])


class DailySummaryManager(BaseManager[DailySummary]):
    """Data access for DailySummary entities."""

    entity = DailySummary

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def _select_with_names(self):
        return select(DailySummary, Housing.name.label("housing_name")).join(
            Housing, DailySummary.housing_id == Housing.id
        )

    @staticmethod
    def _attach_names(summary: DailySummary, housing_name: Optional[str]) -> DailySummary:
        summary.housing_name = housing_name
        return summary

    async def search_with_names(
        self,
        order_by: Optional[list[str]] = None,
        pagination: Optional[PaginationParams] = None,
        **filters,
    ) -> list[DailySummary]:
        """Search summaries and attach joined housing_name label."""
        stmt = self._select_with_names()
        stmt = self.apply_filters(stmt, **filters)
        if order_by:
            stmt = self.apply_ordering(stmt, order_by)
        if pagination:
            stmt = get_paginated_query(stmt, pagination)

        rows = (await self.db.execute(stmt)).all()
        return [self._attach_names(row[0], row[1]) for row in rows]

    async def get_by_id_with_names(self, summary_id: UUID) -> Optional[DailySummary]:
        """Fetch a single daily summary enriched with housing_name."""
        stmt = self._select_with_names().where(DailySummary.id == summary_id)
        row = (await self.db.execute(stmt)).first()
        if row is None:
            return None
        return self._attach_names(row[0], row[1])
