"""
Сервис сверки план/факт
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import func
from uuid import UUID
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..models.housing import Housing, Section, Floor
from ..models.work import WorkType
from ..models.contractor import Contractor
from ..models.plan import PlanItem
from ..models.fact import WorkFact
from ..models.reconciliation import (
    ReconciliationResult, 
    DailySummary,
    ReconciliationStatus,
    ReconciliationPattern
)


def classify_status(
    planned_volume: Decimal,
    actual_volume: Decimal,
    has_plan: bool,
    has_fact: bool
) -> Tuple[ReconciliationStatus, Decimal]:
    """
    Классифицирует статус выполнения работы.
    
    Args:
        planned_volume: Плановый объём
        actual_volume: Фактический объём
        has_plan: Есть ли план
        has_fact: Есть ли факт
    
    Returns:
        Tuple[ReconciliationStatus, Decimal]: (статус, коэффициент выполнения)
    """
    # NO_REPORT: план есть, факт не подан
    if has_plan and not has_fact:
        return ReconciliationStatus.NO_REPORT, Decimal("0")
    
    # UNPLANNED: плана нет, факт подан
    if not has_plan and has_fact:
        return ReconciliationStatus.UNPLANNED, Decimal("0")
    
    # Если нет ни плана ни факта (не должно быть)
    if not has_plan and not has_fact:
        return ReconciliationStatus.NO_REPORT, Decimal("0")
    
    # Рассчитываем completion ratio
    if planned_volume > 0:
        completion_ratio = actual_volume / planned_volume
    else:
        completion_ratio = Decimal("0")
    
    # NOT_DONE: план есть, факт = 0
    if actual_volume == 0:
        return ReconciliationStatus.NOT_DONE, Decimal("0")
    
    # DONE_OVER: > 105%
    if completion_ratio > Decimal("1.05"):
        return ReconciliationStatus.DONE_OVER, completion_ratio
    
    # DONE_FULL: >= 95%
    if completion_ratio >= Decimal("0.95"):
        return ReconciliationStatus.DONE_FULL, completion_ratio
    
    # DONE_PARTIAL: 0 < ratio < 95%
    return ReconciliationStatus.DONE_PARTIAL, completion_ratio


def detect_patterns(
    status: ReconciliationStatus,
    plan_section_id: Optional[UUID],
    fact_section_id: Optional[UUID],
    plan_floor_id: Optional[UUID],
    fact_floor_id: Optional[UUID],
    plan_work_id: Optional[UUID],
    fact_work_id: Optional[UUID]
) -> Optional[ReconciliationPattern]:
    """
    Определяет паттерны ошибок.
    
    Args:
        status: Статус выполнения
        plan_section_id: ID секции по плану
        fact_section_id: ID секции по факту
        plan_floor_id: ID этажа по плану
        fact_floor_id: ID этажа по факту
        plan_work_id: ID работы по плану
        fact_work_id: ID работы по факту
    
    Returns:
        Optional[ReconciliationPattern]: Паттерн или None
    """
    # Только для внеплановых работ
    if status != ReconciliationStatus.UNPLANNED:
        return None
    
    # WRONG_WORK_TYPE: Работа другого типа
    if plan_work_id and fact_work_id and plan_work_id != fact_work_id:
        return ReconciliationPattern.WRONG_WORK_TYPE
    
    # WRONG_LOCATION: Работа в другом месте
    if (plan_section_id and fact_section_id and plan_section_id != fact_section_id) or \
       (plan_floor_id and fact_floor_id and plan_floor_id != fact_floor_id):
        return ReconciliationPattern.WRONG_LOCATION
    
    return None


async def match_plans_and_facts(
    target_date: date,
    housing_id: Optional[UUID],
    db: AsyncSession
) -> List[Dict]:
    """
    Сопоставляет планы и факты.
    
    Args:
        target_date: Дата сверки
        housing_id: ID корпуса (None = все корпуса)
        db: Сессия БД
    
    Returns:
        List[Dict]: Список сопоставленных записей
    """
    # Получаем планы
    plans_query = select(PlanItem).where(PlanItem.date == target_date)
    if housing_id:
        plans_query = plans_query.where(PlanItem.housing_id == housing_id)
    
    plans_result = await db.execute(plans_query)
    plans = plans_result.scalars().all()
    
    # Получаем факты
    facts_query = select(WorkFact).where(WorkFact.date == target_date)
    if housing_id:
        facts_query = facts_query.where(WorkFact.housing_id == housing_id)
    
    facts_result = await db.execute(facts_query)
    facts = facts_result.scalars().all()
    
    # Создаём словарь планов по ключу
    plans_dict = {}
    for plan in plans:
        key = (
            plan.contractor_id,
            plan.section_id,
            plan.floor_id,
            plan.work_type_id
        )
        plans_dict[key] = plan
    
    # Создаём словарь фактов по ключу
    facts_dict = {}
    for fact in facts:
        key = (
            fact.contractor_id,
            fact.section_id,
            fact.floor_id,
            fact.work_type_id
        )
        facts_dict[key] = fact
    
    # Сопоставление
    matches = []
    
    # 1. Проходим по планам
    for key, plan in plans_dict.items():
        fact = facts_dict.get(key)
        
        if fact:
            # Есть и план и факт
            matches.append({
                "key": key,
                "contractor_id": plan.contractor_id,
                "section_id": plan.section_id,
                "floor_id": plan.floor_id,
                "work_type_id": plan.work_type_id,
                "housing_id": plan.housing_id,
                "plan": plan,
                "fact": fact,
                "has_plan": True,
                "has_fact": True
            })
            # Удаляем из словаря фактов, чтобы не обработать дважды
            del facts_dict[key]
        else:
            # Есть план, нет факта
            matches.append({
                "key": key,
                "contractor_id": plan.contractor_id,
                "section_id": plan.section_id,
                "floor_id": plan.floor_id,
                "work_type_id": plan.work_type_id,
                "housing_id": plan.housing_id,
                "plan": plan,
                "fact": None,
                "has_plan": True,
                "has_fact": False
            })
    
    # 2. Оставшиеся факты без планов (внеплановые)
    for key, fact in facts_dict.items():
        matches.append({
            "key": key,
            "contractor_id": fact.contractor_id,
            "section_id": fact.section_id,
            "floor_id": fact.floor_id,
            "work_type_id": fact.work_type_id,
            "housing_id": fact.housing_id,
            "plan": None,
            "fact": fact,
            "has_plan": False,
            "has_fact": True
        })
    
    return matches


async def build_summary(
    target_date: date,
    housing_id: UUID,
    results: List[ReconciliationResult],
    db: AsyncSession
) -> DailySummary:
    """
    Строит сводку дня.
    
    Args:
        target_date: Дата
        housing_id: ID корпуса
        results: Результаты сверки
        db: Сессия БД
    
    Returns:
        DailySummary: Сводка дня
    """
    # Подсчёт по статусам
    total_planned = 0
    total_done_full = 0
    total_done_partial = 0
    total_done_over = 0
    total_not_done = 0
    total_no_report = 0
    total_unplanned = 0
    
    # Объёмы для взвешенного completion
    total_planned_volume = Decimal("0")
    total_actual_volume = Decimal("0")
    
    # Подрядчики
    contractors_stats = {}
    
    for result in results:
        # Подсчёт статусов
        if result.status == ReconciliationStatus.DONE_FULL:
            total_done_full += 1
        elif result.status == ReconciliationStatus.DONE_PARTIAL:
            total_done_partial += 1
        elif result.status == ReconciliationStatus.DONE_OVER:
            total_done_over += 1
        elif result.status == ReconciliationStatus.NOT_DONE:
            total_not_done += 1
        elif result.status == ReconciliationStatus.NO_REPORT:
            total_no_report += 1
        elif result.status == ReconciliationStatus.UNPLANNED:
            total_unplanned += 1
        
        # Подсчёт планов
        if result.plan_item_id:
            total_planned += 1
        
        # Объёмы
        if result.planned_volume:
            total_planned_volume += result.planned_volume
        if result.actual_volume:
            total_actual_volume += result.actual_volume
        
        # Статистика по подрядчикам
        contractor_id = str(result.contractor_id)
        if contractor_id not in contractors_stats:
            contractors_stats[contractor_id] = {
                "total": 0,
                "done_full": 0,
                "done_partial": 0,
                "done_over": 0,
                "not_done": 0,
                "no_report": 0,
                "unplanned": 0
            }
        
        contractors_stats[contractor_id]["total"] += 1
        if result.status == ReconciliationStatus.DONE_FULL:
            contractors_stats[contractor_id]["done_full"] += 1
        elif result.status == ReconciliationStatus.DONE_PARTIAL:
            contractors_stats[contractor_id]["done_partial"] += 1
        elif result.status == ReconciliationStatus.DONE_OVER:
            contractors_stats[contractor_id]["done_over"] += 1
        elif result.status == ReconciliationStatus.NOT_DONE:
            contractors_stats[contractor_id]["not_done"] += 1
        elif result.status == ReconciliationStatus.NO_REPORT:
            contractors_stats[contractor_id]["no_report"] += 1
        elif result.status == ReconciliationStatus.UNPLANNED:
            contractors_stats[contractor_id]["unplanned"] += 1
    
    # Рассчитываем метрики
    completion_rate = Decimal("0")
    if total_planned > 0:
        completion_rate = Decimal((total_done_full + total_done_over) / total_planned * 100)
    
    weighted_completion = Decimal("0")
    if total_planned_volume > 0:
        weighted_completion = Decimal(total_actual_volume / total_planned_volume * 100)
    
    submission_rate = Decimal("0")
    if total_planned > 0:
        submission_rate = Decimal((total_planned - total_no_report) / total_planned * 100)
    
    # Создаём сводку
    summary = DailySummary(
        date=target_date,
        housing_id=housing_id,
        total_planned=total_planned,
        total_done_full=total_done_full,
        total_done_partial=total_done_partial,
        total_done_over=total_done_over,
        total_not_done=total_not_done,
        total_no_report=total_no_report,
        total_unplanned=total_unplanned,
        completion_rate=completion_rate,
        weighted_completion=weighted_completion,
        submission_rate=submission_rate,
        contractor_details=contractors_stats,
        alerts=[]  # Заполняется в сервисе алертов
    )
    
    return summary


async def run_reconciliation(
    target_date: date,
    housing_id: Optional[UUID],
    db: AsyncSession
) -> Dict:
    """
    Запускает полную сверку план/факт.
    
    Args:
        target_date: Дата сверки
        housing_id: ID корпуса (None = все корпуса)
        db: Сессия БД
    
    Returns:
        Dict: Результаты сверки
    """
    # 1. Получаем список корпусов для сверки
    if housing_id:
        housing_ids = [housing_id]
    else:
        housings_result = await db.execute(select(Housing.id))
        housing_ids = [h for h in housings_result.scalars().all()]
    
    total_results = 0
    total_summaries = 0
    
    # 2. Для каждого корпуса
    for hid in housing_ids:
        # Сопоставляем планы и факты
        matches = await match_plans_and_facts(target_date, hid, db)
        
        # Обрабатываем каждое сопоставление
        results = []
        for match in matches:
            plan = match.get("plan")
            fact = match.get("fact")
            
            planned_volume = plan.planned_volume if plan else Decimal("0")
            actual_volume = fact.actual_volume if fact else Decimal("0")
            
            # Классифицируем статус
            status, completion_ratio = classify_status(
                planned_volume,
                actual_volume,
                match["has_plan"],
                match["has_fact"]
            )
            
            # Определяем паттерны
            pattern = detect_patterns(
                status,
                plan.section_id if plan else None,
                fact.section_id if fact else None,
                plan.floor_id if plan else None,
                fact.floor_id if fact else None,
                plan.work_type_id if plan else None,
                fact.work_type_id if fact else None
            )
            
            # Проверяем опоздание факта
            fact_is_late = False
            fact_submitted_at = None
            if fact:
                fact_submitted_at = fact.submitted_at
                # Считаем опоздавшим, если подан после 20:00 дня работ
                deadline = datetime.combine(target_date, datetime.min.time().replace(hour=20))
                if fact.submitted_at > deadline:
                    fact_is_late = True
            
            # Создаём результат сверки
            result = ReconciliationResult(
                date=target_date,
                housing_id=match["housing_id"],
                section_id=match["section_id"],
                floor_id=match["floor_id"],
                work_type_id=match["work_type_id"],
                contractor_id=match["contractor_id"],
                planned_volume=planned_volume,
                actual_volume=actual_volume,
                completion_ratio=completion_ratio,
                status=status,
                pattern=pattern,
                plan_item_id=plan.id if plan else None,
                work_fact_id=fact.id if fact else None,
                fact_submitted_at=fact_submitted_at,
                fact_is_late=fact_is_late
            )
            
            db.add(result)
            results.append(result)
        
        await db.commit()
        total_results += len(results)
        
        # Строим сводку
        summary = await build_summary(target_date, hid, results, db)
        db.add(summary)
        await db.commit()
        total_summaries += 1
    
    return {
        "date": target_date,
        "housing_count": len(housing_ids),
        "total_results": total_results,
        "total_summaries": total_summaries
    }