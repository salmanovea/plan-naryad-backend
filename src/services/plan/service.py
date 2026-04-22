from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.config.settings import app_config
from src.models import managers
from src.models.dbo.tables.plan import PlanSource, PlanStatus
from src.models.dbo.tables.work import DependencyType
from src.services.common import BaseService

PRIORITY_STARTED = 1000
PRIORITY_OVERDUE = 500
PRIORITY_DEADLINE = 300


class AutogenerationService(BaseService):
    def __init__(self, db: AsyncSession):
        self.plan_item_manager = managers.PlanItemManager(db)
        self.work_fact_manager = managers.WorkFactManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.work_type_manager = managers.WorkTypeManager(db)
        self.tech_sequence_manager = managers.TechSequenceItemManager(db)
        self.contractor_assignment_manager = managers.ContractorAssignmentManager(db)
        self.contractor_manager = managers.ContractorManager(db)
        self.plan_adjustment_manager = managers.PlanAdjustmentManager(db)

    def _is_available(
        self,
        section_id: UUID,
        floor_id: UUID,
        work_type_id: UUID,
        tech_sequence: List[Dict],
        progress: Dict[Tuple[UUID, UUID, UUID], Dict],
    ) -> bool:
        sequence_item = next((i for i in tech_sequence if i["work_type_id"] == work_type_id), None)
        if not sequence_item:
            return False

        for dep_work_id in sequence_item.get("depends_on", []):
            key = (UUID(dep_work_id), section_id, floor_id)
            if key not in progress:
                return False
            dep_progress = progress[key]
            if dep_progress.get("completion_ratio", 0) < Decimal("0.95"):
                return False
            if sequence_item.get("dependency_type") == DependencyType.FINISH_TO_START:
                last_fact_date = dep_progress.get("last_fact_date")
                if last_fact_date:
                    lag_days = sequence_item.get("lag_days", 0)
                    if date.today() < last_fact_date + timedelta(days=lag_days):
                        return False
        return True

    @staticmethod
    def _priority_score(
        work_type_id: UUID,
        section_id: UUID,
        floor_id: UUID,
        progress: Dict[Tuple[UUID, UUID, UUID], Dict],
        deadline_date: Optional[date] = None,
    ) -> int:
        key = (work_type_id, section_id, floor_id)
        if key in progress:
            completion = progress[key].get("completion_ratio", 0)
            if Decimal("0") < completion < Decimal("1.0"):
                return PRIORITY_STARTED
        if deadline_date and deadline_date < date.today():
            return PRIORITY_OVERDUE + min((date.today() - deadline_date).days * 10, 400)
        if deadline_date:
            days_to = (deadline_date - date.today()).days
            if days_to <= 7:
                return PRIORITY_DEADLINE + (7 - days_to) * 20
        return 100

    async def _assign_contractor(
        self,
        housing_id: UUID,
        section_id: UUID,
        work_type_id: UUID,
        work_group_id: UUID,
    ) -> Optional[UUID]:
        assignments = await self.contractor_assignment_manager.search(
            housing_id=housing_id,
            work_group_id=work_group_id,
            section_id=section_id,
        )
        if not assignments:
            assignments = await self.contractor_assignment_manager.search(
                housing_id=housing_id,
                work_group_id=work_group_id,
                section_id__isnull=True,
            )

        assignment = assignments[0] if assignments else None
        if not assignment:
            return None

        if assignment.work_type_ids:
            return assignment.contractor_id if str(work_type_id) in assignment.work_type_ids else None
        return assignment.contractor_id

    def _calculate_daily_volume(
        self,
        work_type_id: UUID,
        section_id: UUID,
        floor_id: UUID,
        tech_sequence: List[Dict],
        progress: Dict[Tuple[UUID, UUID, UUID], Dict],
    ) -> Tuple[Decimal, Decimal]:
        sequence_item = next((i for i in tech_sequence if i["work_type_id"] == work_type_id), None)
        if not sequence_item:
            return Decimal("0"), Decimal("0")

        daily_norm = sequence_item.get("daily_norm_volume", Decimal("0"))
        total_volume = sequence_item.get("total_volume", Decimal("0"))
        key = (work_type_id, section_id, floor_id)
        completed = progress[key].get("actual_volume", Decimal("0")) if key in progress else Decimal("0")
        return daily_norm, min(daily_norm, total_volume - completed)

    async def generate_daily_plan(self, housing_id: UUID, target_date: date) -> List:
        if target_date.weekday() >= 5:
            return []

        existing = await self.plan_item_manager.search(housing_id=housing_id, date=target_date)
        if existing:
            return existing

        housing = await self.housing_manager.get_by_id(housing_id)
        if not housing:
            return []

        sections = await self.section_manager.search(
            housing_id=housing_id, order_by=["section_number"]
        )
        tech_sequence_items = await self.tech_sequence_manager.search(
            housing_id=housing_id, order_by=["order"]
        )

        tech_sequence: List[Dict] = []
        prev_work_type_id = None
        for item in tech_sequence_items:
            depends_on = [str(prev_work_type_id)] if prev_work_type_id else []
            tech_sequence.append({
                "work_type_id": item.work_type_id,
                "depends_on": depends_on,
                "dependency_type": item.dependency_type,
                "lag_days": item.lag_days,
                "daily_norm_volume": item.daily_norm_volume,
                "total_volume": item.total_volume,
                "estimated_days": item.estimated_days,
            })
            prev_work_type_id = item.work_type_id

        facts = await self.work_fact_manager.search(housing_id=housing_id, date__lt=target_date)

        progress: Dict[Tuple[UUID, UUID, UUID], Dict] = {}
        for fact in facts:
            key = (fact.work_type_id, fact.section_id, fact.floor_id)
            if key not in progress:
                progress[key] = {"actual_volume": Decimal("0"), "last_fact_date": fact.date}
            progress[key]["actual_volume"] += fact.actual_volume
            if fact.date > progress[key]["last_fact_date"]:
                progress[key]["last_fact_date"] = fact.date

        work_type_ids = [item.work_type_id for item in tech_sequence_items]
        plans = await self.plan_item_manager.search(
            housing_id=housing_id, work_type_id__in=work_type_ids
        )
        planned_volumes: Dict[Tuple[UUID, UUID, UUID], Decimal] = {}
        for plan in plans:
            key = (plan.work_type_id, plan.section_id, plan.floor_id)
            planned_volumes.setdefault(key, Decimal("0"))
            planned_volumes[key] += plan.planned_volume

        for key in progress:
            pv = planned_volumes.get(key, Decimal("0"))
            progress[key]["completion_ratio"] = progress[key]["actual_volume"] / pv if pv > 0 else Decimal("0")

        plan_items_data = []
        contractor_counts: Dict[UUID, int] = {}
        max_per_contractor = app_config.max_items_per_contractor

        for section in sections:
            floors = await self.floor_manager.search(
                section_id=section.id, order_by=["floor_number"]
            )
            for floor in floors:
                for seq_item in tech_sequence:
                    work_type_id = seq_item["work_type_id"]
                    if not self._is_available(section.id, floor.id, work_type_id, tech_sequence, progress):
                        continue

                    work_type = await self.work_type_manager.get_by_id(work_type_id)
                    if not work_type:
                        continue

                    contractor_id = await self._assign_contractor(
                        housing_id, section.id, work_type_id, work_type.group_id
                    )
                    if not contractor_id:
                        continue

                    contractor_counts.setdefault(contractor_id, 0)
                    if contractor_counts[contractor_id] >= max_per_contractor:
                        continue

                    _, daily_volume = self._calculate_daily_volume(
                        work_type_id, section.id, floor.id, tech_sequence, progress
                    )
                    if daily_volume <= Decimal("0"):
                        continue

                    plan_items_data.append({
                        "date": target_date,
                        "housing_id": housing_id,
                        "section_id": section.id,
                        "floor_id": floor.id,
                        "work_type_id": work_type_id,
                        "contractor_id": contractor_id,
                        "planned_volume": daily_volume,
                        "unit": work_type.unit,
                        "source": PlanSource.AUTO,
                        "status": PlanStatus.DRAFT,
                    })
                    contractor_counts[contractor_id] += 1

        if plan_items_data:
            await self.plan_item_manager.bulk_insert(plan_items_data, is_commit=True)

        return await self.plan_item_manager.search(housing_id=housing_id, date=target_date)


async def get_plan_service(db: AsyncSession = Depends(get_session)) -> AutogenerationService:
    return AutogenerationService(db=db)
