"""
Сервис автогенерации план-наряда
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import func
from uuid import UUID
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..models.housing import Housing, Section, Floor
from ..models.work import WorkType, TechSequenceItem, WorkGroup, DependencyType
from ..models.contractor import Contractor, ContractorAssignment
from ..models.plan import PlanItem, PlanSource, PlanStatus
from ..models.fact import WorkFact

# Константы
MAX_ITEMS_PER_CONTRACTOR = 10
PRIORITY_STARTED = 1000  # Продолжение начатых работ
PRIORITY_OVERDUE = 500   # Просроченные работы
PRIORITY_DEADLINE = 300  # Работы с дедлайном
DAILY_WORK_HOURS = 8     # Рабочий день в часах


async def is_available(
    section_id: UUID,
    floor_id: UUID,
    work_type_id: UUID,
    tech_sequence: List[Dict],
    progress: Dict[Tuple[UUID, UUID, UUID], Dict]
) -> bool:
    """
    Проверяет, доступна ли работа для выполнения на данной секции/этаже.
    
    Args:
        section_id: ID секции
        floor_id: ID этажа
        work_type_id: ID вида работ
        tech_sequence: Технологическая последовательность
        progress: Словарь прогресса по работам {(work_id, section_id, floor_id): данные}
    
    Returns:
        bool: True если работа доступна
    """
    # Находим элемент техпоследовательности для этой работы
    sequence_item = None
    for item in tech_sequence:
        if item["work_type_id"] == work_type_id:
            sequence_item = item
            break
    
    if not sequence_item:
        return False
    
    # Проверяем зависимости
    for dep_work_id in sequence_item.get("depends_on", []):
        # Проверяем, завершена ли зависимая работа
        key = (UUID(dep_work_id), section_id, floor_id)
        if key not in progress:
            return False
        
        dep_progress = progress[key]
        if dep_progress.get("completion_ratio", 0) < Decimal("0.95"):  # < 95% выполнено
            return False
        
        # Проверяем lag days если есть
        if sequence_item.get("dependency_type") == DependencyType.FINISH_TO_START:
            last_fact_date = dep_progress.get("last_fact_date")
            if last_fact_date:
                lag_days = sequence_item.get("lag_days", 0)
                min_date = last_fact_date + timedelta(days=lag_days)
                if date.today() < min_date:
                    return False
    
    return True


def priority_score(
    work_type_id: UUID,
    section_id: UUID,
    floor_id: UUID,
    progress: Dict[Tuple[UUID, UUID, UUID], Dict],
    deadline_date: Optional[date] = None
) -> int:
    """
    Рассчитывает приоритетный балл для работы.
    
    Args:
        work_type_id: ID вида работ
        section_id: ID секции
        floor_id: ID этажа
        progress: Словарь прогресса
        deadline_date: Дата дедлайна
    
    Returns:
        int: Приоритетный балл
    """
    key = (work_type_id, section_id, floor_id)
    
    # 1. Продолжение начатых работ (самый высокий приоритет)
    if key in progress:
        completion = progress[key].get("completion_ratio", 0)
        if completion > 0 and completion < Decimal("1.0"):
            return PRIORITY_STARTED
    
    # 2. Просроченные работы
    if deadline_date and deadline_date < date.today():
        days_overdue = (date.today() - deadline_date).days
        return PRIORITY_OVERDUE + min(days_overdue * 10, 400)  # Максимум +400
    
    # 3. Работы с дедлайном
    if deadline_date:
        days_to_deadline = (deadline_date - date.today()).days
        if days_to_deadline <= 7:  # Неделя до дедлайна
            return PRIORITY_DEADLINE + (7 - days_to_deadline) * 20
    
    # 4. Остальные работы
    return 100


async def assign_contractor(
    housing_id: UUID,
    section_id: UUID,
    floor_id: UUID,
    work_type_id: UUID,
    work_group_id: UUID,
    db: AsyncSession
) -> Optional[UUID]:
    """
    Находит подрядчика для работы.
    
    Args:
        housing_id: ID корпуса
        section_id: ID секции
        floor_id: ID этажа
        work_type_id: ID вида работ
        work_group_id: ID группы работ
    
    Returns:
        Optional[UUID]: ID подрядчика или None
    """
    # Ищем привязки подрядчиков
    assignments_query = select(ContractorAssignment).where(
        ContractorAssignment.housing_id == housing_id,
        ContractorAssignment.work_group_id == work_group_id
    )
    
    # Сначала ищем привязку к конкретной секции
    section_specific = await db.execute(
        assignments_query.where(ContractorAssignment.section_id == section_id)
    )
    assignment = section_specific.scalars().first()
    
    # Если нет привязки к секции, ищем общую привязку к корпусу
    if not assignment:
        general = await db.execute(
            assignments_query.where(ContractorAssignment.section_id.is_(None))
        )
        assignment = general.scalars().first()
    
    if assignment:
        # Проверяем, есть ли конкретные виды работ в assignment
        if assignment.work_type_ids:
            if str(work_type_id) in assignment.work_type_ids:
                return assignment.contractor_id
            else:
                return None
        else:
            # Если не указаны конкретные виды, используем все
            return assignment.contractor_id
    
    return None


async def calculate_daily_volume(
    housing_id: UUID,
    section_id: UUID,
    floor_id: UUID,
    work_type_id: UUID,
    tech_sequence: List[Dict],
    progress: Dict[Tuple[UUID, UUID, UUID], Dict],
    db: AsyncSession
) -> Tuple[Decimal, Decimal]:
    """
    Рассчитывает дневной объём работ.
    
    Args:
        housing_id: ID корпуса
        section_id: ID секции
        floor_id: ID этажа
        work_type_id: ID вида работ
        tech_sequence: Технологическая последовательность
        progress: Словарь прогресса
    
    Returns:
        Tuple[Decimal, Decimal]: (дневная норма, остаток до завершения)
    """
    # Находим элемент техпоследовательности
    sequence_item = None
    for item in tech_sequence:
        if item["work_type_id"] == work_type_id:
            sequence_item = item
            break
    
    if not sequence_item:
        return Decimal("0"), Decimal("0")
    
    daily_norm = sequence_item.get("daily_norm_volume", Decimal("0"))
    total_volume = sequence_item.get("total_volume", Decimal("0"))
    
    # Рассчитываем остаток
    key = (work_type_id, section_id, floor_id)
    if key in progress:
        completed = progress[key].get("actual_volume", Decimal("0"))
        remaining = total_volume - completed
    else:
        remaining = total_volume
    
    # Ограничиваем дневной объём остатком
    daily_volume = min(daily_norm, remaining)
    
    return daily_norm, daily_volume


async def generate_daily_plan(
    session: AsyncSession = None,
    housing_id: UUID = None,
    target_date: date = None,
    db: AsyncSession = None
) -> List[PlanItem]:
    # Support both 'session' and 'db' parameter names
    if db is None:
        db = session
    """
    Основная функция генерации план-наряда на день.
    
    Args:
        housing_id: ID корпуса
        target_date: Дата плана
        db: Сессия БД
    
    Returns:
        List[PlanItem]: Список строк план-наряда
    """
    # Проверяем, не выходной ли день (упрощённо)
    if target_date.weekday() >= 5:  # Суббота или воскресенье
        # В реальном приложении здесь может быть проверка производственного календаря
        return []
    
    # 1. Получаем структуру корпуса
    housing_result = await db.execute(
        select(Housing).where(Housing.id == housing_id)
    )
    housing_obj = housing_result.scalar_one()
    
    sections_result = await db.execute(
        select(Section).where(Section.housing_id == housing_id).order_by(Section.section_number)
    )
    sections = sections_result.scalars().all()
    
    # 2. Получаем технологическую последовательность
    tech_seq_result = await db.execute(
        select(TechSequenceItem)
        .where(TechSequenceItem.housing_id == housing_id)
        .order_by(TechSequenceItem.order)
    )
    tech_sequence_items = tech_seq_result.scalars().all()
    
    # Преобразуем в словарь для удобства
    tech_sequence = []
    prev_work_type_id = None
    for item in tech_sequence_items:
        # Build depends_on from order (each item depends on the previous one)
        depends_on = [str(prev_work_type_id)] if prev_work_type_id else []
        tech_sequence.append({
            "work_type_id": item.work_type_id,
            "depends_on": depends_on,
            "dependency_type": item.dependency_type,
            "lag_days": item.lag_days,
            "daily_norm_volume": item.daily_norm_volume,
            "total_volume": item.total_volume,
            "estimated_days": item.estimated_days
        })
        prev_work_type_id = item.work_type_id
    
    # 3. Получаем прогресс выполнения работ
    # Запрашиваем факты выполнения
    facts_query = select(WorkFact).where(
        WorkFact.housing_id == housing_id,
        WorkFact.date < target_date
    )
    facts_result = await db.execute(facts_query)
    facts = facts_result.scalars().all()
    
    # Собираем прогресс по работам
    progress = {}
    for fact in facts:
        key = (fact.work_type_id, fact.section_id, fact.floor_id)
        if key not in progress:
            progress[key] = {
                "actual_volume": Decimal("0"),
                "last_fact_date": fact.date
            }
        
        progress[key]["actual_volume"] += fact.actual_volume
        if fact.date > progress[key]["last_fact_date"]:
            progress[key]["last_fact_date"] = fact.date
    
    # Добавляем информацию о планах для расчёта completion_ratio
    plans_query = select(PlanItem).where(
        PlanItem.housing_id == housing_id,
        PlanItem.work_type_id.in_([item.work_type_id for item in tech_sequence_items])
    )
    plans_result = await db.execute(plans_query)
    plans = plans_result.scalars().all()
    
    # Собираем плановые объёмы
    planned_volumes = {}
    for plan in plans:
        key = (plan.work_type_id, plan.section_id, plan.floor_id)
        if key not in planned_volumes:
            planned_volumes[key] = Decimal("0")
        planned_volumes[key] += plan.planned_volume
    
    # Рассчитываем completion ratio
    for key in progress:
        if key in planned_volumes and planned_volumes[key] > 0:
            progress[key]["completion_ratio"] = progress[key]["actual_volume"] / planned_volumes[key]
        else:
            progress[key]["completion_ratio"] = Decimal("0")
    
    # 4. Генерируем план-наряд
    plan_items = []
    contractor_counts = {}  # Счётчик items per contractor
    
    # Для каждой секции и этажа
    for section in sections:
        floors_result = await db.execute(
            select(Floor).where(Floor.section_id == section.id).order_by(Floor.floor_number)
        )
        floors = floors_result.scalars().all()
        
        for floor in floors:
            # Для каждой работы в техпоследовательности
            for seq_item in tech_sequence:
                work_type_id = seq_item["work_type_id"]
                
                # Проверяем доступность
                if not await is_available(
                    section.id, floor.id, work_type_id, tech_sequence, progress
                ):
                    continue
                
                # Получаем информацию о виде работ
                work_type_result = await db.execute(
                    select(WorkType).where(WorkType.id == work_type_id)
                )
                work_type = work_type_result.scalar_one()
                
                # Назначаем подрядчика
                contractor_id = await assign_contractor(
                    housing_id, section.id, floor.id, work_type_id, work_type.group_id, db
                )
                
                if not contractor_id:
                    continue
                
                # Проверяем лимит на подрядчика
                if contractor_id not in contractor_counts:
                    contractor_counts[contractor_id] = 0
                
                if contractor_counts[contractor_id] >= MAX_ITEMS_PER_CONTRACTOR:
                    continue
                
                # Рассчитываем объём
                daily_norm, daily_volume = await calculate_daily_volume(
                    housing_id, section.id, floor.id, work_type_id, tech_sequence, progress, db
                )
                
                if daily_volume <= Decimal("0"):
                    continue
                
                # Создаём план-наряд
                plan_item = PlanItem(
                    date=target_date,
                    housing_id=housing_id,
                    section_id=section.id,
                    floor_id=floor.id,
                    work_type_id=work_type_id,
                    contractor_id=contractor_id,
                    planned_volume=daily_volume,
                    unit=work_type.unit,
                    source=PlanSource.AUTO,
                    status=PlanStatus.DRAFT
                )
                
                plan_items.append(plan_item)
                contractor_counts[contractor_id] += 1
    
    # Сохраняем в БД
    for item in plan_items:
        db.add(item)
    
    await db.commit()
    
    # Обновляем объекты для возврата
    for item in plan_items:
        await db.refresh(item)
    
    return plan_items