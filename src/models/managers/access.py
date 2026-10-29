"""Explicit assignment queries used by domain services.

These queries never wrap CRUD or arbitrary caller queries. Each service chooses its own
filter and passes it to the ordinary manager before pagination or aggregation.
"""

from collections.abc import Collection
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, exists, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ReadOnlyColumnCollection
from sqlalchemy.sql.elements import ColumnElement

from src.models.dbo import models as m
from src.models.managers.common import BaseManager

IdQuery = Select[tuple[UUID]]
Columns = ReadOnlyColumnCollection[str, Any]


class AccessManager(BaseManager[m.Project]):
    """Resolve Raport assignments and validate explicit selections."""

    entity = m.Project

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def project_ids(self, projects: Collection[str]) -> IdQuery:
        """Local projects corresponding to assigned Raport identifiers."""
        return (select(m.Project.id).where(m.Project.raport_id.in_(projects))).correlate(None)

    def _project_condition(self, columns: Columns, projects: Collection[str]) -> ColumnElement[bool]:
        clauses = [columns.project_id.in_(self.project_ids(projects))]
        for field, parent in (("construction_object_id", m.ConstructionObject), ("queue_id", m.Queue)):
            if field not in columns:
                continue
            table = parent.__table__.alias()
            matches = exists(
                select(table.c.id)
                .where(table.c.id == columns[field], table.c.project_id == columns.project_id)
                .correlate(columns.project_id.table)
            )
            clauses.append(or_(columns[field].is_(None), matches))
        return and_(*clauses)

    def object_ids(self, projects: Collection[str]) -> IdQuery:
        """Objects inside assigned projects with a consistent project/queue pair."""
        return (
            select(m.ConstructionObject.id).where(self._project_condition(m.ConstructionObject.__table__.c, projects))
        ).correlate(None)

    def housing_ids(self, projects: Collection[str]) -> IdQuery:
        """Housings belonging to the assigned project hierarchy."""
        return (select(m.Housing.id).where(m.Housing.construction_object_id.in_(self.object_ids(projects)))).correlate(
            None
        )

    def section_ids(self, projects: Collection[str]) -> IdQuery:
        """Sections below accessible housings."""
        return (select(m.Section.id).where(m.Section.housing_id.in_(self.housing_ids(projects)))).correlate(None)

    def floor_ids(self, projects: Collection[str]) -> IdQuery:
        """Floors below accessible sections."""
        return (select(m.Floor.id).where(m.Floor.section_id.in_(self.section_ids(projects)))).correlate(None)

    def _location_condition(self, columns: Columns, projects: Collection[str]) -> ColumnElement[bool]:
        clauses = [columns.housing_id.in_(self.housing_ids(projects))]
        if "section_id" in columns:
            section = m.Section.__table__.alias()
            clauses.append(
                or_(
                    columns.section_id.is_(None),
                    columns.section_id.in_(
                        select(section.c.id)
                        .where(section.c.housing_id == columns.housing_id)
                        .correlate(columns.housing_id.table)
                    ),
                )
            )
        if "floor_id" in columns:
            floor = m.Floor.__table__.alias()
            clauses.append(
                columns.floor_id.in_(
                    select(floor.c.id)
                    .where(floor.c.section_id == columns.section_id)
                    .correlate(columns.housing_id.table)
                )
            )
        return and_(*clauses)

    def plan_item_ids(self, projects: Collection[str], contractors: Collection[str] | None = None) -> IdQuery:
        """Plan positions in assigned projects, with the contractor feed restrictions."""
        query = select(m.PlanItem.id).where(self._location_condition(m.PlanItem.__table__.c, projects))
        if contractors is not None:
            query = query.where(
                m.PlanItem.contractor_id.in_(self.contractor_ids(projects, contractors)),
                m.PlanItem.status == m.PlanStatus.TRANSFERRED.value,
            )
        return (query).correlate(None)

    def budget_item_ids(self, projects: Collection[str]) -> IdQuery:
        """Budget lines matching both their period and construction object's project."""
        period, obj = m.BudgetPeriod.__table__.alias(), m.ConstructionObject.__table__.alias()
        matching_object = exists(
            select(obj.c.id)
            .where(obj.c.id == m.BudgetItem.construction_object_id, obj.c.project_id == period.c.project_id)
            .correlate(period, m.BudgetItem.__table__)
        )
        periods = (
            select(period.c.id)
            .where(
                period.c.project_id.in_(self.project_ids(projects)),
                or_(m.BudgetItem.construction_object_id.is_(None), matching_object),
            )
            .correlate(m.BudgetItem.__table__)
        )
        return (select(m.BudgetItem.id).where(m.BudgetItem.budget_period_id.in_(periods))).correlate(None)

    def contractor_ids(
        self, projects: Collection[str], contractors: Collection[str] | None = None, grants: Collection[str] = ()
    ) -> IdQuery:
        """Companies assigned to the caller or referenced by accessible project data."""
        if contractors is not None:
            return (select(m.Contractor.id).where(m.Contractor.raport_id.in_(contractors))).correlate(None)
        references: list[Select] = [
            select(m.PlanItem.contractor_id).where(m.PlanItem.id.in_(self.plan_item_ids(projects))),
            select(m.WorkFact.contractor_id).where(m.WorkFact.id.in_(self.work_fact_ids(projects))),
            select(m.ReconciliationResult.contractor_id).where(
                m.ReconciliationResult.id.in_(self.result_ids(projects))
            ),
            select(m.Alert.contractor_id).where(m.Alert.id.in_(self.alert_ids(projects))),
            select(m.HeadcountFact.contractor_id).where(m.HeadcountFact.id.in_(self.headcount_fact_ids(projects))),
            select(m.HeadcountPlan.contractor_id).where(m.HeadcountPlan.id.in_(self.headcount_plan_ids(projects))),
            select(m.Violation.contractor_id).where(m.Violation.id.in_(self.violation_ids(projects))),
            select(m.ContractorAssignment.contractor_id).where(
                m.ContractorAssignment.id.in_(self.assignment_ids(projects))
            ),
            select(m.BudgetItem.contractor_id).where(m.BudgetItem.id.in_(self.budget_item_ids(projects))),
            select(m.Contractor.id).where(m.Contractor.raport_id.in_(grants)),
        ]
        return (
            select(m.Contractor.id).where(m.Contractor.id.in_(union(*(q.correlate(None) for q in references))))
        ).correlate(None)

    async def ids(self, query: IdQuery) -> list[UUID]:
        """Materialize an ID query for filters that need concrete values."""
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def matching_ids(self, query: IdQuery, requested: Collection[UUID]) -> set[UUID]:
        """Check the whole selection with one query before any business side effect."""
        ids = query.subquery()
        result = await self.db.execute(select(ids.c.id).where(ids.c.id.in_(requested)))
        return set(result.scalars().all())

    def queue_ids(self, projects: Collection[str]) -> IdQuery:
        """Queue records belonging to assigned projects."""
        return (select(m.Queue.id).where(self._project_condition(m.Queue.__table__.c, projects))).correlate(None)

    def budget_period_ids(self, projects: Collection[str]) -> IdQuery:
        """BudgetPeriod records belonging to assigned projects."""
        return (
            select(m.BudgetPeriod.id).where(self._project_condition(m.BudgetPeriod.__table__.c, projects))
        ).correlate(None)

    def headcount_fact_ids(self, projects: Collection[str]) -> IdQuery:
        """HeadcountFact records belonging to assigned projects."""
        return (
            select(m.HeadcountFact.id).where(self._project_condition(m.HeadcountFact.__table__.c, projects))
        ).correlate(None)

    def headcount_plan_ids(self, projects: Collection[str]) -> IdQuery:
        """HeadcountPlan records belonging to assigned projects."""
        return (
            select(m.HeadcountPlan.id).where(self._project_condition(m.HeadcountPlan.__table__.c, projects))
        ).correlate(None)

    def challenge_ids(self, projects: Collection[str]) -> IdQuery:
        """Challenge records belonging to assigned projects."""
        return (select(m.Challenge.id).where(self._project_condition(m.Challenge.__table__.c, projects))).correlate(
            None
        )

    def violation_ids(self, projects: Collection[str]) -> IdQuery:
        """Violation records belonging to assigned projects."""
        return (select(m.Violation.id).where(self._project_condition(m.Violation.__table__.c, projects))).correlate(
            None
        )

    def work_fact_ids(self, projects: Collection[str]) -> IdQuery:
        """WorkFact records with an accessible and consistent housing hierarchy."""
        return (select(m.WorkFact.id).where(self._location_condition(m.WorkFact.__table__.c, projects))).correlate(None)

    def result_ids(self, projects: Collection[str]) -> IdQuery:
        """ReconciliationResult records with an accessible and consistent housing hierarchy."""
        return (
            select(m.ReconciliationResult.id).where(
                self._location_condition(m.ReconciliationResult.__table__.c, projects)
            )
        ).correlate(None)

    def summary_ids(self, projects: Collection[str]) -> IdQuery:
        """DailySummary records with an accessible and consistent housing hierarchy."""
        return (
            select(m.DailySummary.id).where(self._location_condition(m.DailySummary.__table__.c, projects))
        ).correlate(None)

    def alert_ids(self, projects: Collection[str]) -> IdQuery:
        """Alert records with an accessible and consistent housing hierarchy."""
        return (select(m.Alert.id).where(self._location_condition(m.Alert.__table__.c, projects))).correlate(None)

    def tech_sequence_ids(self, projects: Collection[str]) -> IdQuery:
        """TechSequenceItem records with an accessible and consistent housing hierarchy."""
        return (
            select(m.TechSequenceItem.id).where(self._location_condition(m.TechSequenceItem.__table__.c, projects))
        ).correlate(None)

    def assignment_ids(self, projects: Collection[str]) -> IdQuery:
        """Workforce assignments under accessible construction objects."""
        return (
            select(m.ContractorAssignment.id).where(
                m.ContractorAssignment.construction_object_id.in_(self.object_ids(projects))
            )
        ).correlate(None)

    def challenge_item_ids(self, projects: Collection[str]) -> IdQuery:
        """Items belonging to accessible challenges."""
        return (
            select(m.ChallengeItem.id).where(m.ChallengeItem.challenge_id.in_(self.challenge_ids(projects)))
        ).correlate(None)

    def mobilization_plan_ids(self, projects: Collection[str]) -> IdQuery:
        """Mobilization plans belonging to accessible challenge items."""
        return (
            select(m.MobilizationPlan.id).where(
                m.MobilizationPlan.challenge_item_id.in_(self.challenge_item_ids(projects))
            )
        ).correlate(None)

    def checkpoint_ids(self, projects: Collection[str]) -> IdQuery:
        """Checkpoints belonging to accessible mobilization plans."""
        return (
            select(m.MobilizationCheckpoint.id).where(
                m.MobilizationCheckpoint.mobilization_plan_id.in_(self.mobilization_plan_ids(projects))
            )
        ).correlate(None)

    def position_limit_ids(self, projects: Collection[str], grants: Collection[str] = ()) -> IdQuery:
        """Position limits for companies referenced by accessible project data."""
        return (
            select(m.ContractorPositionLimit.id).where(
                m.ContractorPositionLimit.contractor_id.in_(self.contractor_ids(projects, grants=grants))
            )
        ).correlate(None)
