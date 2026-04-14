from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from datetime import date, datetime, timedelta
from typing import Optional, List
from decimal import Decimal

from ..database import get_db
from ..models.housing import Housing
from ..models.contractor import Contractor
from ..models.plan import PlanItem, PlanStatus
from ..models.fact import WorkFact
from ..models.reconciliation import ReconciliationResult, DailySummary, ReconciliationStatus
from ..models.alert import Alert, AlertLevel

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

@router.get("/overview")
async def get_dashboard_overview(
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=7)),
    date_to: date = Query(default_factory=date.today),
    housing_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Сводная информация для дашборда"""
    # Базовые запросы
    plan_query = select(func.count(PlanItem.id)).where(
        PlanItem.date >= date_from,
        PlanItem.date <= date_to
    )
    
    fact_query = select(func.count(WorkFact.id)).where(
        WorkFact.date >= date_from,
        WorkFact.date <= date_to
    )
    
    recon_query = select(func.count(ReconciliationResult.id)).where(
        ReconciliationResult.date >= date_from,
        ReconciliationResult.date <= date_to
    )
    
    alert_query = select(func.count(Alert.id)).where(
        Alert.date >= date_from,
        Alert.date <= date_to
    )
    
    # Применяем фильтр по корпусу если указан
    if housing_id:
        plan_query = plan_query.where(PlanItem.housing_id == housing_id)
        fact_query = fact_query.where(WorkFact.housing_id == housing_id)
        recon_query = recon_query.where(ReconciliationResult.housing_id == housing_id)
        alert_query = alert_query.where(Alert.housing_id == housing_id)
        
        # Проверяем существование корпуса
        housing_result = await db.execute(
            select(Housing).where(Housing.id == housing_id)
        )
        housing = housing_result.scalar_one_or_none()
        if not housing:
            raise HTTPException(status_code=404, detail="Корпус не найден")
    
    # Выполняем запросы
    total_plans = (await db.execute(plan_query)).scalar_one() or 0
    total_facts = (await db.execute(fact_query)).scalar_one() or 0
    total_recons = (await db.execute(recon_query)).scalar_one() or 0
    total_alerts = (await db.execute(alert_query)).scalar_one() or 0
    
    # Подсчёт подтверждённых планов
    confirmed_query = select(func.count(PlanItem.id)).where(
        PlanItem.date >= date_from,
        PlanItem.date <= date_to,
        PlanItem.rs_confirmed == True
    )
    if housing_id:
        confirmed_query = confirmed_query.where(PlanItem.housing_id == housing_id)
    
    confirmed_plans = (await db.execute(confirmed_query)).scalar_one() or 0
    
    # Статистика сверки по статусам
    recon_stats_query = select(
        ReconciliationResult.status,
        func.count(ReconciliationResult.id)
    ).where(
        ReconciliationResult.date >= date_from,
        ReconciliationResult.date <= date_to
    )
    
    if housing_id:
        recon_stats_query = recon_stats_query.where(ReconciliationResult.housing_id == housing_id)
    
    recon_stats_query = recon_stats_query.group_by(ReconciliationResult.status)
    recon_stats_result = await db.execute(recon_stats_query)
    recon_stats = dict(recon_stats_result.all())
    
    # Подсчёт выполненных работ (DONE_FULL + DONE_OVER)
    completed_works = recon_stats.get(ReconciliationStatus.DONE_FULL.value, 0) + \
                     recon_stats.get(ReconciliationStatus.DONE_OVER.value, 0)
    
    # Статистика алертов по уровням
    alert_stats_query = select(
        Alert.level,
        func.count(Alert.id)
    ).where(
        Alert.date >= date_from,
        Alert.date <= date_to
    )
    
    if housing_id:
        alert_stats_query = alert_stats_query.where(Alert.housing_id == housing_id)
    
    alert_stats_query = alert_stats_query.group_by(Alert.level)
    alert_stats_result = await db.execute(alert_stats_query)
    alert_stats = dict(alert_stats_result.all())
    
    # Получаем последние сводки
    summary_query = select(DailySummary).where(
        DailySummary.date >= date_from,
        DailySummary.date <= date_to
    )
    
    if housing_id:
        summary_query = summary_query.where(DailySummary.housing_id == housing_id)
    
    summary_query = summary_query.order_by(DailySummary.date.desc()).limit(7)
    summaries_result = await db.execute(summary_query)
    summaries = summaries_result.scalars().all()
    
    # Рассчитываем средние показатели
    avg_completion = 0
    avg_submission = 0
    
    if summaries:
        avg_completion = sum(s.completion_rate for s in summaries) / len(summaries)
        avg_submission = sum(s.submission_rate for s in summaries) / len(summaries)
    
    return {
        "period": {
            "from": date_from,
            "to": date_to
        },
        "housing_id": housing_id,
        "housing_name": housing.name if housing_id else None,
        "totals": {
            "plans": total_plans,
            "confirmed_plans": confirmed_plans,
            "facts": total_facts,
            "reconciliations": total_recons,
            "alerts": total_alerts
        },
        "reconciliation": {
            "completed_works": completed_works,
            "completion_rate": completed_works / total_recons * 100 if total_recons > 0 else 0,
            "by_status": recon_stats
        },
        "alerts": {
            "critical": alert_stats.get(AlertLevel.CRITICAL.value, 0),
            "warning": alert_stats.get(AlertLevel.WARNING.value, 0),
            "info": alert_stats.get(AlertLevel.INFO.value, 0)
        },
        "metrics": {
            "plan_confirmation_rate": confirmed_plans / total_plans * 100 if total_plans > 0 else 0,
            "fact_submission_rate": total_facts / total_plans * 100 if total_plans > 0 else 0,
            "avg_completion_rate": float(avg_completion),
            "avg_submission_rate": float(avg_submission)
        },
        "recent_summaries": [
            {
                "date": s.date,
                "completion_rate": float(s.completion_rate),
                "submission_rate": float(s.submission_rate),
                "total_planned": s.total_planned
            }
            for s in summaries
        ]
    }

@router.get("/contractors")
async def get_contractors_dashboard(
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
    housing_id: Optional[UUID] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Дашборд по подрядчикам"""
    # Запрос для получения топ подрядчиков по объёму работ
    contractors_query = select(
        Contractor,
        func.count(PlanItem.id).label("total_plans"),
        func.sum(PlanItem.planned_volume).label("total_planned_volume"),
        func.count(WorkFact.id).label("total_facts"),
        func.sum(WorkFact.actual_volume).label("total_actual_volume")
    ).join(
        PlanItem, PlanItem.contractor_id == Contractor.id
    ).join(
        WorkFact, 
        (WorkFact.contractor_id == Contractor.id) & 
        (WorkFact.date >= date_from) & 
        (WorkFact.date <= date_to),
        isouter=True
    ).where(
        PlanItem.date >= date_from,
        PlanItem.date <= date_to
    )
    
    if housing_id:
        contractors_query = contractors_query.where(PlanItem.housing_id == housing_id)
    
    contractors_query = contractors_query.group_by(Contractor.id).order_by(
        func.sum(PlanItem.planned_volume).desc()
    ).limit(limit)
    
    contractors_result = await db.execute(contractors_query)
    contractors_data = contractors_result.all()
    
    # Формируем ответ
    contractors_list = []
    for contractor, total_plans, total_planned, total_facts, total_actual in contractors_data:
        # Получаем статистику сверки для этого подрядчика
        recon_query = select(
            ReconciliationResult.status,
            func.count(ReconciliationResult.id)
        ).where(
            ReconciliationResult.contractor_id == contractor.id,
            ReconciliationResult.date >= date_from,
            ReconciliationResult.date <= date_to
        ).group_by(ReconciliationResult.status)
        
        recon_result = await db.execute(recon_query)
        recon_stats = dict(recon_result.all())
        
        # Рассчитываем показатели
        completion_rate = 0
        if recon_stats:
            completed = recon_stats.get(ReconciliationStatus.DONE_FULL.value, 0) + \
                       recon_stats.get(ReconciliationStatus.DONE_OVER.value, 0)
            total_recon = sum(recon_stats.values())
            completion_rate = completed / total_recon * 100 if total_recon > 0 else 0
        
        contractors_list.append({
            "id": contractor.id,
            "name": contractor.name,
            "short_name": contractor.short_name,
            "contact_person": contractor.contact_person,
            "phone": contractor.phone,
            "stats": {
                "total_plans": total_plans,
                "total_planned_volume": float(total_planned) if total_planned else 0,
                "total_facts": total_facts,
                "total_actual_volume": float(total_actual) if total_actual else 0,
                "completion_rate": completion_rate,
                "reconciliation_stats": recon_stats
            }
        })
    
    return {
        "period": {
            "from": date_from,
            "to": date_to
        },
        "housing_id": housing_id,
        "contractors": contractors_list
    }

@router.get("/rs-performance")
async def get_rs_performance_dashboard(
    date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    date_to: date = Query(default_factory=date.today),
    housing_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Производительность РС (руководителей строительства)"""
    # В реальном приложении здесь была бы статистика по конкретным пользователям РС
    # Сейчас возвращаем общую статистику
    
    # Подсчёт планов по дням
    daily_plans_query = select(
        PlanItem.date,
        func.count(PlanItem.id).label("total_plans"),
        func.sum(PlanItem.planned_volume).label("total_volume")
    ).where(
        PlanItem.date >= date_from,
        PlanItem.date <= date_to
    )
    
    if housing_id:
        daily_plans_query = daily_plans_query.where(PlanItem.housing_id == housing_id)
    
    daily_plans_query = daily_plans_query.group_by(PlanItem.date).order_by(PlanItem.date)
    daily_plans_result = await db.execute(daily_plans_query)
    daily_plans = daily_plans_result.all()
    
    # Статистика подтверждения планов
    confirmation_stats_query = select(
        func.count(PlanItem.id).label("total"),
        func.count(PlanItem.id).filter(PlanItem.rs_confirmed == True).label("confirmed")
    ).where(
        PlanItem.date >= date_from,
        PlanItem.date <= date_to
    )
    
    if housing_id:
        confirmation_stats_query = confirmation_stats_query.where(PlanItem.housing_id == housing_id)
    
    confirmation_stats_result = await db.execute(confirmation_stats_query)
    total_plans, confirmed_plans = confirmation_stats_result.one()
    
    # Время подтверждения (среднее)
    # В реальном приложении нужно хранить время создания и подтверждения
    
    return {
        "period": {
            "from": date_from,
            "to": date_to
        },
        "housing_id": housing_id,
        "overall_stats": {
            "total_plans": total_plans or 0,
            "confirmed_plans": confirmed_plans or 0,
            "confirmation_rate": confirmed_plans / total_plans * 100 if total_plans else 0,
            "avg_confirmation_time_hours": 24,  # Заглушка
            "plans_per_day": (total_plans or 0) / max((date_to - date_from).days, 1)
        },
        "daily_plans": [
            {
                "date": date,
                "total_plans": count,
                "total_volume": float(volume) if volume else 0
            }
            for date, count, volume in daily_plans
        ]
    }