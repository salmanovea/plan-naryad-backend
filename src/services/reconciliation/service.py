from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo.tables.reconciliation import ReconciliationPattern, ReconciliationStatus
from src.services.common import BaseService


class ReconciliationService(BaseService):
    def __init__(self, db: AsyncSession):
        self.plan_item_manager = managers.PlanItemManager(db)
        self.work_fact_manager = managers.WorkFactManager(db)
        self.reconciliation_manager = managers.ReconciliationResultManager(db)
        self.daily_summary_manager = managers.DailySummaryManager(db)
        self.housing_manager = managers.HousingManager(db)

    @staticmethod
    def classify_status(
        planned_volume: Decimal,
        actual_volume: Decimal,
        has_plan: bool,
        has_fact: bool,
    ) -> Tuple[ReconciliationStatus, Decimal]:
        if has_plan and not has_fact:
            return ReconciliationStatus.NO_REPORT, Decimal("0")
        if not has_plan and has_fact:
            return ReconciliationStatus.UNPLANNED, Decimal("0")
        if not has_plan and not has_fact:
            return ReconciliationStatus.NO_REPORT, Decimal("0")

        completion_ratio = actual_volume / planned_volume if planned_volume > 0 else Decimal("0")

        if actual_volume == 0:
            return ReconciliationStatus.NOT_DONE, Decimal("0")
        if completion_ratio > Decimal("1.05"):
            return ReconciliationStatus.DONE_OVER, completion_ratio
        if completion_ratio >= Decimal("0.95"):
            return ReconciliationStatus.DONE_FULL, completion_ratio
        return ReconciliationStatus.DONE_PARTIAL, completion_ratio

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

    async def _match_plans_and_facts(
        self,
        target_date: date,
        housing_id: Optional[UUID],
    ) -> List[Dict]:
        plans = await self.plan_item_manager.search(date=target_date, housing_id=housing_id)
        facts = await self.work_fact_manager.search(date=target_date, housing_id=housing_id)

        plans_dict = {(p.contractor_id, p.section_id, p.floor_id, p.work_type_id): p for p in plans}
        facts_dict = {(f.contractor_id, f.section_id, f.floor_id, f.work_type_id): f for f in facts}

        matches = []
        for key, plan in plans_dict.items():
            fact = facts_dict.pop(key, None)
            matches.append(
                {
                    "contractor_id": plan.contractor_id,
                    "section_id": plan.section_id,
                    "floor_id": plan.floor_id,
                    "work_type_id": plan.work_type_id,
                    "housing_id": plan.housing_id,
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
                    "work_type_id": fact.work_type_id,
                    "housing_id": fact.housing_id,
                    "plan": None,
                    "fact": fact,
                    "has_plan": False,
                    "has_fact": True,
                }
            )

        return matches

    def _build_summary_data(
        self,
        target_date: date,
        housing_id: UUID,
        results_data: List[Dict],
    ) -> Dict:
        counts = {s: 0 for s in ReconciliationStatus}
        total_planned = 0
        total_planned_volume = Decimal("0")
        total_actual_volume = Decimal("0")
        contractors_stats: Dict[str, Dict] = {}

        for r in results_data:
            status = r["status"]
            counts[status] = counts.get(status, 0) + 1
            if r.get("plan_item_id"):
                total_planned += 1
            if r.get("planned_volume"):
                total_planned_volume += r["planned_volume"]
            if r.get("actual_volume"):
                total_actual_volume += r["actual_volume"]

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
        done_over = counts.get(ReconciliationStatus.DONE_OVER, 0)
        no_report = counts.get(ReconciliationStatus.NO_REPORT, 0)

        completion_rate = Decimal((done_full + done_over) / total_planned * 100) if total_planned > 0 else Decimal("0")
        weighted_completion = (
            Decimal(total_actual_volume / total_planned_volume * 100) if total_planned_volume > 0 else Decimal("0")
        )
        submission_rate = (
            Decimal((total_planned - no_report) / total_planned * 100) if total_planned > 0 else Decimal("0")
        )

        return {
            "date": target_date,
            "housing_id": housing_id,
            "total_planned": total_planned,
            "total_done_full": done_full,
            "total_done_partial": counts.get(ReconciliationStatus.DONE_PARTIAL, 0),
            "total_done_over": done_over,
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
        target_date: date,
        housing_id: Optional[UUID],
    ) -> Dict:
        if housing_id:
            housing_ids = [housing_id]
        else:
            housings = await self.housing_manager.search()
            housing_ids = [h.id for h in housings]

        total_results = 0
        total_summaries = 0

        for hid in housing_ids:
            matches = await self._match_plans_and_facts(target_date, hid)
            results_data = []

            for match in matches:
                plan = match.get("plan")
                fact = match.get("fact")
                planned_volume = plan.planned_volume if plan else Decimal("0")
                actual_volume = fact.actual_volume if fact else Decimal("0")

                status, completion_ratio = self.classify_status(
                    planned_volume, actual_volume, match["has_plan"], match["has_fact"]
                )
                pattern = self.detect_patterns(
                    status,
                    plan.section_id if plan else None,
                    fact.section_id if fact else None,
                    plan.floor_id if plan else None,
                    fact.floor_id if fact else None,
                    plan.work_type_id if plan else None,
                    fact.work_type_id if fact else None,
                )

                fact_is_late = False
                fact_submitted_at = None
                if fact:
                    fact_submitted_at = fact.submitted_at
                    deadline = datetime.combine(target_date, datetime.min.time().replace(hour=20))
                    if fact.submitted_at and fact.submitted_at > deadline:
                        fact_is_late = True

                row = {
                    "date": target_date,
                    "housing_id": match["housing_id"],
                    "section_id": match["section_id"],
                    "floor_id": match["floor_id"],
                    "work_type_id": match["work_type_id"],
                    "contractor_id": match["contractor_id"],
                    "planned_volume": planned_volume,
                    "actual_volume": actual_volume,
                    "completion_ratio": completion_ratio,
                    "status": status,
                    "pattern": pattern,
                    "plan_item_id": plan.id if plan else None,
                    "work_fact_id": fact.id if fact else None,
                    "fact_submitted_at": fact_submitted_at,
                    "fact_is_late": fact_is_late,
                }
                results_data.append(row)

            if results_data:
                await self.reconciliation_manager.bulk_insert(results_data, is_commit=True)
            total_results += len(results_data)

            summary_data = self._build_summary_data(target_date, hid, results_data)
            await self.daily_summary_manager.create(summary_data)
            total_summaries += 1

        return {
            "date": target_date,
            "housing_count": len(housing_ids),
            "total_results": total_results,
            "total_summaries": total_summaries,
        }


async def get_reconciliation_service(db: AsyncSession = Depends(get_session)) -> ReconciliationService:
    return ReconciliationService(db=db)
