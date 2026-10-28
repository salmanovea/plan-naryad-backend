from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import Select, Text, cast, false, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.dbo.tables.reconciliation import DailySummary, ReconciliationResult
from src.models.managers.access import IdQuery
from src.models.managers.common import BaseManager


class ReconciliationResultManager(BaseManager[ReconciliationResult]):
    """Data access for ReconciliationResult entities."""

    entity = ReconciliationResult

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def get_enriched_query(self) -> Select:
        """Base query eager-loading the relations needed to denormalize labels.

        Loads section/floor/work/contractor/housing so the service can fill
        the `*_name` fields without lazy-loading inside an async context.
        """
        return select(ReconciliationResult).options(
            selectinload(ReconciliationResult.section),
            selectinload(ReconciliationResult.floor),
            selectinload(ReconciliationResult.work),
            selectinload(ReconciliationResult.contractor),
            selectinload(ReconciliationResult.housing),
        )

    async def get_enriched_by_id(self, result_id: UUID) -> Optional[ReconciliationResult]:
        """Fetch a single result by id with its label relations eager-loaded."""
        query = self.get_enriched_query().where(ReconciliationResult.id == result_id)
        rows = await self.fetch(query)
        return rows[0] if rows else None

    async def delete_by_date_and_housing(
        self, target_date: date, housing_id: UUID, allowed_ids: IdQuery | None = None
    ) -> int:
        """Delete all results for a (date, housing); returns the count removed."""
        existing = await self.search(date=target_date, housing_id=housing_id, id__in=allowed_ids)
        ids = [e.id for e in existing]
        await self.bulk_delete(ids)
        return len(ids)


class DailySummaryManager(BaseManager[DailySummary]):
    """Data access for DailySummary entities."""

    entity = DailySummary

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def get_enriched_query(self) -> Select:
        """Base query eager-loading `housing` so `housing_name` can be filled.

        `DailySummarySchema` carries the housing name; a lazy load during serialisation
        fails with MissingGreenlet outside the async context.
        """
        return select(DailySummary).options(selectinload(DailySummary.housing))

    @staticmethod
    def with_contractors(query: Select, contractor_ids: list[UUID]) -> Select:
        """Keep the summaries in which any of the contractors has a row.

        SQL: `WHERE CAST(contractor_details AS JSONB) ?| ARRAY[:contractor_ids]`.
        """
        if not contractor_ids:
            return query.where(false())
        keys = cast([str(c) for c in contractor_ids], ARRAY(Text))
        return query.where(cast(DailySummary.contractor_details, JSONB).has_any(keys))

    async def get_enriched_by_id(self, summary_id: UUID) -> Optional[DailySummary]:
        """Fetch a single summary by id with its housing eager-loaded."""
        query = self.get_enriched_query().where(DailySummary.id == summary_id)
        rows = await self.fetch(query)
        return rows[0] if rows else None

    async def delete_by_date_and_housing(
        self, target_date: date, housing_id: UUID, allowed_ids: IdQuery | None = None
    ) -> int:
        """Delete all summaries for a (date, housing); returns the count removed."""
        existing = await self.search(date=target_date, housing_id=housing_id, id__in=allowed_ids)
        ids = [e.id for e in existing]
        await self.bulk_delete(ids)
        return len(ids)
