from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import Row, Select, Text, cast, false, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.dbo.tables.reconciliation import DailySummary, ReconciliationResult, ReconciliationStatus
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

    async def get_last_plan_days(
        self, housing_id: UUID, before: date, days: int, allowed_ids: IdQuery | None = None
    ) -> list[ReconciliationResult]:
        """Planned rows of each contractor's last `days` days with positions before `before`.

        SQL:
            WITH ranked AS (
                SELECT contractor_id, date,
                       DENSE_RANK() OVER (PARTITION BY contractor_id ORDER BY date DESC) AS rank
                FROM reconciliation_results
                WHERE housing_id = :housing_id AND date < :before AND status <> 'UNPLANNED'
            )
            SELECT r.* FROM reconciliation_results r
            JOIN (SELECT DISTINCT contractor_id, date FROM ranked WHERE rank <= :days) d
              ON d.contractor_id = r.contractor_id AND d.date = r.date
            WHERE r.housing_id = :housing_id AND r.status <> 'UNPLANNED'
        """
        planned = (ReconciliationResult.housing_id == housing_id) & (
            ReconciliationResult.status != ReconciliationStatus.UNPLANNED.value
        )
        ranked = select(
            ReconciliationResult.contractor_id,
            ReconciliationResult.date,
            func.dense_rank()
            .over(partition_by=ReconciliationResult.contractor_id, order_by=ReconciliationResult.date.desc())
            .label("rank"),
        ).where(planned, ReconciliationResult.date < before)
        if allowed_ids is not None:
            ranked = ranked.where(ReconciliationResult.id.in_(allowed_ids))
        ranked_days = ranked.subquery()
        last_days = (
            select(ranked_days.c.contractor_id, ranked_days.c.date)
            .where(ranked_days.c.rank <= days)
            .distinct()
            .subquery()
        )
        query = (
            select(ReconciliationResult)
            .join(
                last_days,
                (last_days.c.contractor_id == ReconciliationResult.contractor_id)
                & (last_days.c.date == ReconciliationResult.date),
            )
            .where(planned)
        )
        if allowed_ids is not None:
            query = query.where(ReconciliationResult.id.in_(allowed_ids))
        return await self.fetch(query)

    async def get_contractor_totals(self, **filters) -> list[Row]:
        """Per-contractor counts of the four summary indicators over the filtered rows.

        Every row that is not UNPLANNED came from a plan item, which is what keeps the counts
        equal to the results table even after a plan item is deleted and its link nulled.

        SQL:
            SELECT contractor_id,
                   COUNT(*) FILTER (WHERE status <> 'UNPLANNED') AS issued,
                   COUNT(*) FILTER (WHERE status NOT IN ('UNPLANNED', 'NO_REPORT')) AS reported,
                   COUNT(*) FILTER (WHERE status = 'NO_REPORT') AS not_reported,
                   COUNT(*) FILTER (WHERE status = 'UNPLANNED') AS unplanned
            FROM reconciliation_results WHERE <filters> GROUP BY contractor_id
        """
        status = ReconciliationResult.status
        unplanned = ReconciliationStatus.UNPLANNED.value
        no_report = ReconciliationStatus.NO_REPORT.value
        query = select(
            ReconciliationResult.contractor_id,
            func.count().filter(status != unplanned).label("issued"),
            func.count().filter(status.not_in([unplanned, no_report])).label("reported"),
            func.count().filter(status == no_report).label("not_reported"),
            func.count().filter(status == unplanned).label("unplanned"),
        ).group_by(ReconciliationResult.contractor_id)
        query = self.apply_filters(query, **filters)
        return list((await self.db.execute(query)).all())


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

    async def get_dates(self, **filters) -> set[date]:
        """Distinct days that hold a summary — the days reconciliation was run for.

        SQL: `SELECT DISTINCT date FROM daily_summaries WHERE <filters>`.
        """
        query = self.apply_filters(select(DailySummary.date).distinct(), **filters)
        return set((await self.db.execute(query)).scalars().all())

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
