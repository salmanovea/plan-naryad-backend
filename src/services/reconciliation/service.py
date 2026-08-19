from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemes import PaginationParams
from src.api.v1.reconciliation.schemes import DailySummarySchema, ReconciliationResultSchema
from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo.tables.reconciliation import ReconciliationPattern, ReconciliationResult, ReconciliationStatus
from src.services.common import BaseService, floor_label
from src.services.report_cells import CellKey, HousingSlice, ReportCellsService


DONE_PERCENT = Decimal("100")


def _fraction(percent: Optional[Decimal]) -> Decimal:
    """A 0..100 percent as a 0..1 fraction, the scale the rates are stored in."""
    if percent is None:
        return Decimal("0")
    return (percent / DONE_PERCENT).quantize(Decimal("0.0001"))


class ReconciliationService(BaseService):
    def __init__(self, db: AsyncSession):
        self.plan_item_manager = managers.PlanItemManager(db)
        self.work_fact_manager = managers.WorkFactManager(db)
        self.reconciliation_manager = managers.ReconciliationResultManager(db)
        self.daily_summary_manager = managers.DailySummaryManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.work_manager = managers.WorkManager(db)
        self.contractor_manager = managers.ContractorManager(db)
        self.construction_object_manager = managers.ConstructionObjectManager(db)
        self.report_cells = ReportCellsService(db)

    @staticmethod
    def _enrich_result(result: ReconciliationResult) -> ReconciliationResultSchema:
        """Map a result (with relations loaded) to a schema with readable labels."""
        schema = ReconciliationResultSchema.model_validate(result)
        floor = result.floor
        if floor:
            schema.floor_number = floor.floor_number
            schema.floor_name = floor_label(floor)
        schema.section_name = result.section.name if result.section else None
        schema.work_name = result.work.name if result.work else None
        schema.contractor_name = result.contractor.name if result.contractor else None
        schema.housing_name = result.housing.name if result.housing else None
        return schema

    async def list_results(
        self,
        pagination: PaginationParams,
        order_by: List[str],
        **filters,
    ) -> Tuple[List[ReconciliationResultSchema], int]:
        """List reconciliation results with denormalized section/floor/etc labels."""
        query = self.reconciliation_manager.get_enriched_query()
        items = await self.reconciliation_manager.search(
            query=query, order_by=order_by, pagination=pagination, **filters
        )
        total = await self.reconciliation_manager.count(**filters)
        return [self._enrich_result(i) for i in items], total

    async def filter_options(
        self,
        housing_id: Optional[UUID] = None,
        project_id: Optional[UUID] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> dict:
        """Values present in a reconciled scope, one list per filterable column.

        Built from distinct ids rather than from the rows the browser holds: the results
        table is paginated on the server, so a filter assembled client-side would only ever
        offer what the current page happens to show.
        """
        filters: dict = {}
        if housing_id:
            filters["housing_id"] = housing_id
        elif project_id:
            housing_ids = await self._housings_in_scope(None, project_id)
            filters["housing_id__in"] = housing_ids or [UUID(int=0)]
        if date_from:
            filters["date__gte"] = date_from
        if date_to:
            filters["date__lte"] = date_to

        rows = await self.reconciliation_manager.search(**filters)
        if not rows:
            return {"statuses": [], "patterns": [], "works": [], "sections": [], "floors": [], "contractors": []}

        statuses = sorted({r.status.value if hasattr(r.status, "value") else str(r.status) for r in rows})
        patterns = sorted(
            {(p.value if hasattr(p, "value") else str(p)) for p in (r.pattern for r in rows) if p is not None}
        )

        works = await self.work_manager.get_enriched_by_ids(list({r.work_id for r in rows if r.work_id}))
        sections = await self.section_manager.get_by_ids(list({r.section_id for r in rows if r.section_id}))
        floors = await self.floor_manager.get_by_ids(list({r.floor_id for r in rows if r.floor_id}))
        contractors = await self.contractor_manager.get_by_ids(list({r.contractor_id for r in rows if r.contractor_id}))

        return {
            "statuses": statuses,
            "patterns": patterns,
            "works": [
                {
                    "id": w.id,
                    "name": w.name,
                    "work_type_name": w.work_type.name if w.work_type else None,
                    "work_group_name": (
                        w.work_type.work_group.name if w.work_type and w.work_type.work_group else None
                    ),
                    "work_set_name": (
                        w.work_type.work_group.work_set.name
                        if w.work_type and w.work_type.work_group and w.work_type.work_group.work_set
                        else None
                    ),
                }
                for w in sorted(works, key=lambda w: w.name)
            ],
            "sections": [{"id": s.id, "name": s.name} for s in sorted(sections, key=lambda s: s.name)],
            "floors": [
                {
                    "id": f.id,
                    "name": floor_label(f) or "",
                    "section_id": f.section_id,
                    "floor_number": f.floor_number,
                }
                for f in sorted(floors, key=lambda f: (f.section_id.hex, f.floor_number))
            ],
            "contractors": [{"id": c.id, "name": c.name} for c in sorted(contractors, key=lambda c: c.name)],
        }

    @staticmethod
    def _enrich_summary(summary) -> DailySummarySchema:
        """Map a summary (with housing loaded) to a schema with the readable name."""
        schema = DailySummarySchema.model_validate(summary)
        schema.housing_name = summary.housing.name if summary.housing else None
        return schema

    async def list_summaries(
        self,
        pagination: PaginationParams,
        order_by: List[str],
        **filters,
    ) -> Tuple[List[DailySummarySchema], int]:
        """List daily summaries with the denormalized housing name."""
        query = self.daily_summary_manager.get_enriched_query()
        items = await self.daily_summary_manager.search(
            query=query, order_by=order_by, pagination=pagination, **filters
        )
        total = await self.daily_summary_manager.count(**filters)
        return [self._enrich_summary(i) for i in items], total

    async def get_summary(self, summary_id: UUID) -> Optional[DailySummarySchema]:
        """Fetch a single daily summary with the denormalized housing name."""
        summary = await self.daily_summary_manager.get_enriched_by_id(summary_id)
        return self._enrich_summary(summary) if summary else None

    async def get_result(self, result_id: UUID) -> Optional[ReconciliationResultSchema]:
        """Fetch a single reconciliation result with denormalized labels."""
        result = await self.reconciliation_manager.get_enriched_by_id(result_id)
        return self._enrich_result(result) if result else None

    @staticmethod
    def classify_status(
        source_percent: Optional[Decimal],
        fact_percent: Optional[Decimal],
        has_plan: bool,
        has_fact: bool,
    ) -> Tuple[ReconciliationStatus, Decimal]:
        """Classify one plan/fact pair by the **growth of the cell percent** (decision Р6c).

        The old rule divided fact volume by planned volume, but the spec removed the volume
        field from a position, so there is no denominator left. What remains is «% Исходный»
        (the percent when the plan was generated) and «% Факт» (the percent now).

        `DONE_OVER` is gone: Raport clamps the percent at 100, so overachievement is not
        representable.

        Returns (status, completion_ratio) where the ratio is the 0..1 fraction of the fact
        percent — kept for the dashboard, which still speaks in rates.
        """
        if not has_plan and has_fact:
            return ReconciliationStatus.UNPLANNED, _fraction(fact_percent)
        if not has_fact:
            return ReconciliationStatus.NO_REPORT, Decimal("0")

        current = fact_percent if fact_percent is not None else Decimal("0")
        before = source_percent if source_percent is not None else Decimal("0")

        if current >= DONE_PERCENT:
            return ReconciliationStatus.DONE_FULL, _fraction(current)
        if current > before:
            return ReconciliationStatus.DONE_PARTIAL, _fraction(current)
        # Facts exist but the percent did not move — the contractor reported nothing useful.
        return ReconciliationStatus.NOT_DONE, _fraction(current)

    @staticmethod
    def detect_patterns(
        status: ReconciliationStatus,
        plan_section_id: Optional[UUID],
        fact_section_id: Optional[UUID],
        plan_floor_id: Optional[UUID],
        fact_floor_id: Optional[UUID],
        plan_work_id: Optional[UUID],
        fact_work_id: Optional[UUID],
    ) -> Optional[ReconciliationPattern]:
        if status != ReconciliationStatus.UNPLANNED:
            return None
        if plan_work_id and fact_work_id and plan_work_id != fact_work_id:
            return ReconciliationPattern.WRONG_WORK_TYPE
        if (plan_section_id and fact_section_id and plan_section_id != fact_section_id) or (
            plan_floor_id and fact_floor_id and plan_floor_id != fact_floor_id
        ):
            return ReconciliationPattern.WRONG_LOCATION
        return None

    def _build_summary_data(
        self,
        target_date: date,
        housing_id: UUID,
        results_data: List[Dict],
    ) -> Dict:
        counts = {s: 0 for s in ReconciliationStatus}
        total_planned = 0
        fact_percents: List[Decimal] = []
        contractors_stats: Dict[str, Dict] = {}

        for r in results_data:
            status = r["status"]
            counts[status] = counts.get(status, 0) + 1
            if r.get("plan_item_id"):
                total_planned += 1
                if r.get("fact_percent") is not None:
                    fact_percents.append(r["fact_percent"])

            cid = str(r["contractor_id"])
            if cid not in contractors_stats:
                status_keys = (
                    "total",
                    "done_full",
                    "done_partial",
                    "done_over",
                    "not_done",
                    "no_report",
                    "unplanned",
                )
                contractors_stats[cid] = {k: 0 for k in status_keys}
            contractors_stats[cid]["total"] += 1
            status_key = status.value.lower() if hasattr(status, "value") else str(status).lower()
            if status_key in contractors_stats[cid]:
                contractors_stats[cid][status_key] += 1

        done_full = counts.get(ReconciliationStatus.DONE_FULL, 0)
        no_report = counts.get(ReconciliationStatus.NO_REPORT, 0)

        quant = Decimal("0.0001")
        completion_rate = (
            (Decimal(done_full) / Decimal(total_planned)).quantize(quant) if total_planned > 0 else Decimal("0")
        )
        weighted_completion = (
            (sum(fact_percents) / (Decimal(len(fact_percents)) * DONE_PERCENT)).quantize(quant)
            if fact_percents
            else Decimal("0")
        )
        submission_rate = (
            (Decimal(total_planned - no_report) / Decimal(total_planned)).quantize(quant)
            if total_planned > 0
            else Decimal("0")
        )

        return {
            "date": target_date,
            "housing_id": housing_id,
            "total_planned": total_planned,
            "total_done_full": done_full,
            "total_done_partial": counts.get(ReconciliationStatus.DONE_PARTIAL, 0),
            "total_done_over": 0,
            "total_not_done": counts.get(ReconciliationStatus.NOT_DONE, 0),
            "total_no_report": no_report,
            "total_unplanned": counts.get(ReconciliationStatus.UNPLANNED, 0),
            "completion_rate": completion_rate,
            "weighted_completion": weighted_completion,
            "submission_rate": submission_rate,
            "contractor_details": contractors_stats,
            "alerts": [],
        }

    async def run_reconciliation(
        self,
        date_from: date,
        date_to: Optional[date] = None,
        housing_id: Optional[UUID] = None,
        project_id: Optional[UUID] = None,
    ) -> Dict:
        """Reconcile a housing (or every housing) over a date range.

        The spec's «Сверка» screen asks for a project, a housing and a **date range**, then a
        «Запустить сверку» button — so this walks the range day by day and rebuilds it whole.

        «% Факт» is defined by the spec as the cell percent **at the moment the reconciliation
        is run**, which is one snapshot for the whole range, not a value per day. The
        chessboard is therefore read once per housing, and only for the works that actually
        appear in the range's plans and facts — not all 657 of the sequence.
        """
        date_to = date_to or date_from
        if date_to < date_from:
            date_from, date_to = date_to, date_from

        housing_ids = await self._housings_in_scope(housing_id, project_id)
        days = [date_from + timedelta(days=offset) for offset in range((date_to - date_from).days + 1)]

        total_results = 0
        total_summaries = 0

        for hid in housing_ids:
            plans = await self.plan_item_manager.search(housing_id=hid, date__gte=date_from, date__lte=date_to)
            facts = await self.work_fact_manager.search(
                housing_id=hid, work_date__gte=date_from, work_date__lte=date_to
            )
            if not plans and not facts:
                continue

            work_ids = {p.work_id for p in plans} | {f.work_id for f in facts}
            slice_ = await self.report_cells.get_housing_slice(hid, work_ids=list(work_ids))

            plans_by_day: Dict[date, list] = {}
            facts_by_day: Dict[date, list] = {}
            for plan in plans:
                plans_by_day.setdefault(plan.date, []).append(plan)
            for fact in facts:
                facts_by_day.setdefault(fact.work_date, []).append(fact)

            for day in days:
                await self.reconciliation_manager.delete_by_date_and_housing(day, hid)
                await self.daily_summary_manager.delete_by_date_and_housing(day, hid)

                results_data = self._build_results(
                    day, hid, plans_by_day.get(day, []), facts_by_day.get(day, []), slice_
                )
                if results_data:
                    await self.reconciliation_manager.bulk_insert(results_data, is_commit=True)
                    total_results += len(results_data)

                summary_data = self._build_summary_data(day, hid, results_data)
                await self.daily_summary_manager.create(summary_data)
                total_summaries += 1

        return {
            "date_from": date_from,
            "date_to": date_to,
            "housing_count": len(housing_ids),
            "total_results": total_results,
            "total_summaries": total_summaries,
        }

    async def _housings_in_scope(
        self,
        housing_id: Optional[UUID],
        project_id: Optional[UUID],
    ) -> list[UUID]:
        """Housings to reconcile: one, all of a project, or every one we know."""
        if housing_id:
            return [housing_id]
        if project_id:
            objects = await self.construction_object_manager.search(project_id=project_id)
            if not objects:
                return []
            housings = await self.housing_manager.search(construction_object_id__in=[o.id for o in objects])
            return [h.id for h in housings]
        return [h.id for h in await self.housing_manager.search()]

    def _build_results(
        self,
        day: date,
        housing_id: UUID,
        plans: list,
        facts: list,
        slice_: HousingSlice,
    ) -> list[Dict]:
        """One day's reconciliation rows for a housing."""
        matches = self._match(plans, facts)
        rows: list[Dict] = []

        for match in matches:
            plan = match.get("plan")
            fact = match.get("fact")

            # «% Исходный» comes from the position; an unplanned row has none.
            source_percent = plan.source_percent if plan else None
            # «% Факт» — the contractor's percent on the cell right now.
            fact_percent = self._current_percent(match, slice_)

            status, completion_ratio = self.classify_status(
                source_percent, fact_percent, match["has_plan"], match["has_fact"]
            )
            pattern = self.detect_patterns(
                status,
                plan.section_id if plan else None,
                fact.section_id if fact else None,
                plan.floor_id if plan else None,
                fact.floor_id if fact else None,
                plan.work_id if plan else None,
                fact.work_id if fact else None,
            )

            fact_submitted_at = fact.submitted_at if fact else None
            fact_is_late = False
            if fact_submitted_at:
                deadline = datetime.combine(day, datetime.min.time().replace(hour=20))
                fact_is_late = fact_submitted_at > deadline

            rows.append(
                {
                    "date": day,
                    "housing_id": housing_id,
                    "section_id": match["section_id"],
                    "floor_id": match["floor_id"],
                    "work_id": match["work_id"],
                    "contractor_id": match["contractor_id"],
                    "source_percent": source_percent,
                    "fact_percent": fact_percent,
                    "completion_ratio": completion_ratio,
                    # Volume columns are on their way out (Р6) — kept at 0 until dropped.
                    "planned_volume": Decimal("0"),
                    "actual_volume": Decimal("0"),
                    "status": status,
                    "pattern": pattern,
                    "plan_item_id": plan.id if plan else None,
                    "work_fact_id": fact.id if fact else None,
                    "fact_submitted_at": fact_submitted_at,
                    "fact_is_late": fact_is_late,
                }
            )
        return rows

    @staticmethod
    def _current_percent(match: Dict, slice_: HousingSlice) -> Optional[Decimal]:
        """Cell percent now: the contractor's own when known, else the cell's best guess."""
        contractor_id = match["contractor_id"]
        if contractor_id:
            state = slice_.cells.get(CellKey(match["section_id"], match["floor_id"], match["work_id"], contractor_id))
            if state:
                return state.percent
        states = slice_.states_on(match["section_id"], match["floor_id"], match["work_id"])
        return max((st.percent for st in states), default=None)

    @staticmethod
    def _match(plans: list, facts: list) -> list[Dict]:
        """Pair plans with facts on (contractor, section, floor, work), per the spec.

        Unmatched rows on either side stay as their own row: a plan without a fact, and a fact
        that was never planned — both are things the screen has to show.
        """
        MatchKey = Tuple[Optional[UUID], UUID, UUID, UUID]
        plans_dict: Dict[MatchKey, Any] = {(p.contractor_id, p.section_id, p.floor_id, p.work_id): p for p in plans}
        facts_dict: Dict[MatchKey, Any] = {(f.contractor_id, f.section_id, f.floor_id, f.work_id): f for f in facts}

        matches: list[Dict] = []
        for key, plan in plans_dict.items():
            fact = facts_dict.pop(key, None)
            matches.append(
                {
                    "contractor_id": plan.contractor_id,
                    "section_id": plan.section_id,
                    "floor_id": plan.floor_id,
                    "work_id": plan.work_id,
                    "plan": plan,
                    "fact": fact,
                    "has_plan": True,
                    "has_fact": fact is not None,
                }
            )
        for key, fact in facts_dict.items():
            matches.append(
                {
                    "contractor_id": fact.contractor_id,
                    "section_id": fact.section_id,
                    "floor_id": fact.floor_id,
                    "work_id": fact.work_id,
                    "plan": None,
                    "fact": fact,
                    "has_plan": False,
                    "has_fact": True,
                }
            )
        return matches


async def get_reconciliation_service(db: AsyncSession = Depends(get_session)) -> ReconciliationService:
    return ReconciliationService(db=db)
