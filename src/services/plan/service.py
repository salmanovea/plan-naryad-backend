from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemes import PaginationParams
from src.api.v1.plan.schemes import PlanItemSchema
from src.config.postgres.db_config import get_session
from src.config.settings import app_config
from src.models import managers
from src.models.dbo.tables.plan import PlanItem, PlanSource, PlanStatus
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

    @staticmethod
    def _enrich_plan_item(item: PlanItem) -> PlanItemSchema:
        """Map a plan item (with relations loaded) to a schema with readable labels."""
        schema = PlanItemSchema.model_validate(item)
        floor = item.floor
        if floor:
            schema.floor_number = floor.floor_number
            schema.floor_name = floor.name or f"Этаж {floor.floor_number}"
        schema.section_name = item.section.name if item.section else None
        schema.work_name = item.work_type.name if item.work_type else None
        schema.contractor_name = item.contractor.name if item.contractor else None
        return schema

    async def list_plan_items(
        self,
        pagination: PaginationParams,
        order_by: List[str],
        **filters,
    ) -> Tuple[List[PlanItemSchema], int]:
        """List plan items with denormalized section/floor/work/contractor names."""
        query = self.plan_item_manager.get_enriched_query()
        items = await self.plan_item_manager.search(query=query, order_by=order_by, pagination=pagination, **filters)
        total = await self.plan_item_manager.count(**filters)
        return [self._enrich_plan_item(i) for i in items], total

    async def get_plan_items(self, order_by: Optional[List[str]] = None, **filters) -> List[PlanItemSchema]:
        """Fetch plan items (no pagination) with denormalized labels."""
        query = self.plan_item_manager.get_enriched_query()
        items = await self.plan_item_manager.search(query=query, order_by=order_by, **filters)
        return [self._enrich_plan_item(i) for i in items]

    async def get_plan_item(self, plan_item_id: UUID) -> Optional[PlanItemSchema]:
        """Fetch a single plan item with denormalized labels."""
        item = await self.plan_item_manager.get_enriched_by_id(plan_item_id)
        return self._enrich_plan_item(item) if item else None

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

    async def generate_daily_plan(
        self,
        housing_id: UUID,
        target_date: date,
        section_id: Optional[UUID] = None,
    ) -> Tuple[List, List[str]]:
        """Generate a day plan, returns (items, reasons).

        When `section_id` is given the plan is generated (and the
        already-generated check is scoped) for that single section only;
        otherwise the whole housing is processed.

        `reasons` is a human-readable list of diagnostic strings explaining
        why the plan ended up empty (no tech_sequence, no contractor
        assignments, weekend, etc.). Empty when items were generated.
        """
        reasons: List[str] = []

        if target_date.weekday() >= 5:
            reasons.append("Дата приходится на выходной — план не генерируется.")
            return [], reasons

        scope: dict = {"housing_id": housing_id, "date": target_date}
        if section_id:
            scope["section_id"] = section_id

        existing = await self.plan_item_manager.search(**scope)
        if existing:
            return existing, reasons

        housing = await self.housing_manager.get_by_id(housing_id)
        if not housing:
            reasons.append("Корпус с таким id не найден.")
            return [], reasons

        if section_id:
            sections = await self.section_manager.search(housing_id=housing_id, id=section_id)
        else:
            sections = await self.section_manager.search(housing_id=housing_id, order_by=["section_number"])
        tech_sequence_items = await self.tech_sequence_manager.search(housing_id=housing_id, order_by=["order"])

        if not sections:
            reasons.append("У корпуса нет секций.")
        if not tech_sequence_items:
            reasons.append(
                "Не настроена техпоследовательность работ для корпуса. "
                "Добавьте записи в tech_sequence_items (POST /api/v1/works/tech-sequence)."
            )

        if not sections or not tech_sequence_items:
            return [], reasons

        tech_sequence: List[Dict] = []
        prev_work_type_id = None
        for item in tech_sequence_items:
            depends_on: List[str] = [str(prev_work_type_id)] if prev_work_type_id else []
            tech_sequence.append(
                {
                    "work_type_id": item.work_type_id,
                    "depends_on": depends_on,
                    "dependency_type": item.dependency_type,
                    "lag_days": item.lag_days,
                    "daily_norm_volume": item.daily_norm_volume,
                    "total_volume": item.total_volume,
                    "estimated_days": item.estimated_days,
                }
            )
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
        plans = await self.plan_item_manager.search(housing_id=housing_id, work_type_id__in=work_type_ids)
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

        # Счётчики причин отказа на уровне (work_type × section × floor) —
        # если ничего не сгенерировалось, агрегированные числа покажут,
        # на чём именно застрял генератор.
        skipped_no_contractor = 0
        skipped_zero_volume = 0
        skipped_dependency = 0
        skipped_contractor_cap = 0
        skipped_unknown_work_type = 0

        for section in sections:
            floors = await self.floor_manager.search(section_id=section.id, order_by=["floor_number"])
            for floor in floors:
                for seq_item in tech_sequence:
                    work_type_id = seq_item["work_type_id"]
                    if not self._is_available(section.id, floor.id, work_type_id, tech_sequence, progress):
                        skipped_dependency += 1
                        continue

                    work_type = await self.work_type_manager.get_by_id(work_type_id)
                    if not work_type:
                        skipped_unknown_work_type += 1
                        continue

                    contractor_id = await self._assign_contractor(
                        housing_id, section.id, work_type_id, work_type.group_id
                    )
                    if not contractor_id:
                        skipped_no_contractor += 1
                        continue

                    contractor_counts.setdefault(contractor_id, 0)
                    if contractor_counts[contractor_id] >= max_per_contractor:
                        skipped_contractor_cap += 1
                        continue

                    _, daily_volume = self._calculate_daily_volume(
                        work_type_id, section.id, floor.id, tech_sequence, progress
                    )
                    if daily_volume <= Decimal("0"):
                        skipped_zero_volume += 1
                        continue

                    plan_items_data.append(
                        {
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
                        }
                    )
                    contractor_counts[contractor_id] += 1

        if plan_items_data:
            await self.plan_item_manager.bulk_insert(plan_items_data, is_commit=True)
            return (
                await self.plan_item_manager.search(**scope),
                reasons,
            )

        # Ничего не сгенерировано — выкатываем читаемый разбор причин.
        if skipped_no_contractor:
            reasons.append(
                f"Не назначен подрядчик для {skipped_no_contractor} (work_type × section). "
                "Добавьте contractor_assignments через UI «Подрядчики на корпусе» или "
                "POST /api/v1/contractors/assignments."
            )
        if skipped_dependency:
            reasons.append(
                f"{skipped_dependency} позиций отложены: предшествующая работа ещё не "
                "завершена (зависимость в техпоследовательности)."
            )
        if skipped_zero_volume:
            reasons.append(f"{skipped_zero_volume} позиций имеют 0 дневной объём (work_type настроен с нулём).")
        if skipped_contractor_cap:
            reasons.append(
                f"{skipped_contractor_cap} позиций отброшено по лимиту max_items_per_contractor={max_per_contractor}."
            )
        if skipped_unknown_work_type:
            reasons.append(f"{skipped_unknown_work_type} позиций ссылаются на несуществующий work_type.")

        if not reasons:
            reasons.append("Не удалось собрать ни одной позиции — данные настроены, но не подходят под фильтры.")

        return [], reasons


async def get_plan_service(db: AsyncSession = Depends(get_session)) -> AutogenerationService:
    return AutogenerationService(db=db)
