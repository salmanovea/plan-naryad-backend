from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import date, datetime, timedelta
from typing import Optional, List

from ..database import get_db
from ..models.alert import Alert, AlertType, AlertLevel, RecipientRole
from ..models.housing import Housing
from ..models.contractor import Contractor
from ..schemas.alert import Alert as AlertSchema, AlertCreate, AlertUpdate, AlertAcknowledge, AlertWithDetails

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

@router.get("/", response_model=list[AlertSchema])
async def get_alerts(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    housing_id: Optional[UUID] = None,
    contractor_id: Optional[UUID] = None,
    alert_type: Optional[AlertType] = None,
    level: Optional[AlertLevel] = None,
    acknowledged: Optional[bool] = None,
    recipient_id: Optional[str] = None,
    recipient_role: Optional[RecipientRole] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Получить алерты с фильтрами"""
    query = select(Alert)
    
    # Применяем фильтры
    if date_from:
        query = query.where(Alert.date >= date_from)
    if date_to:
        query = query.where(Alert.date <= date_to)
    if housing_id:
        query = query.where(Alert.housing_id == housing_id)
    if contractor_id:
        query = query.where(Alert.contractor_id == contractor_id)
    if alert_type:
        query = query.where(Alert.alert_type == alert_type)
    if level:
        query = query.where(Alert.level == level)
    if acknowledged is not None:
        query = query.where(Alert.acknowledged == acknowledged)
    if recipient_id:
        query = query.where(Alert.recipient_id == recipient_id)
    if recipient_role:
        query = query.where(Alert.recipient_role == recipient_role)
    
    # Сортировка и пагинация
    query = query.order_by(
        Alert.level.desc(),  # Критические первыми
        Alert.date.desc(),
        Alert.created_at.desc()
    ).limit(limit).offset(offset)
    
    result = await db.execute(query)
    alerts = result.scalars().all()
    
    # Загружаем детали
    detailed_alerts = []
    for alert in alerts:
        alert_data = {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "level": alert.level,
            "date": alert.date,
            "housing_id": alert.housing_id,
            "contractor_id": alert.contractor_id,
            "rs_user_id": alert.rs_user_id,
            "recipient_id": alert.recipient_id,
            "recipient_role": alert.recipient_role,
            "message": alert.message,
            "channels_sent": alert.channels_sent,
            "sent_at": alert.sent_at,
            "acknowledged": alert.acknowledged,
            "acknowledged_at": alert.acknowledged_at,
            "acknowledged_by": alert.acknowledged_by,
            "escalation_level": alert.escalation_level,
            "escalated_at": alert.escalated_at,
            "created_at": alert.created_at
        }
        
        # Добавляем названия если есть
        if alert.housing_id:
            housing_result = await db.execute(
                select(Housing).where(Housing.id == alert.housing_id)
            )
            housing = housing_result.scalar_one_or_none()
            if housing:
                alert_data["housing_name"] = housing.name
        
        if alert.contractor_id:
            contractor_result = await db.execute(
                select(Contractor).where(Contractor.id == alert.contractor_id)
            )
            contractor = contractor_result.scalar_one_or_none()
            if contractor:
                alert_data["contractor_name"] = contractor.name
        
        detailed_alerts.append(alert_data)
    
    return detailed_alerts

@router.patch("/{alert_id}/acknowledge", response_model=AlertSchema)
async def acknowledge_alert(
    alert_id: UUID,
    acknowledge_data: AlertAcknowledge,
    db: AsyncSession = Depends(get_db)
):
    """Подтвердить получение алерта"""
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Алерт не найден")
    
    if alert.acknowledged:
        raise HTTPException(status_code=400, detail="Алерт уже подтверждён")
    
    # Обновляем статус
    alert.acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = str(acknowledge_data.acknowledged_by)
    
    await db.commit()
    await db.refresh(alert)
    
    return alert

@router.get("/summary")
async def get_alerts_summary(
    date_from: date,
    date_to: date,
    housing_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """Статистика алертов за период"""
    query = select(Alert).where(
        Alert.date >= date_from,
        Alert.date <= date_to
    )
    
    if housing_id:
        query = query.where(Alert.housing_id == housing_id)
    
    result = await db.execute(query)
    alerts = result.scalars().all()
    
    # Статистика по уровням
    by_level = {level.value: 0 for level in AlertLevel}
    by_type = {atype.value: 0 for atype in AlertType}
    by_housing = {}
    
    # Подсчёт
    total = len(alerts)
    acknowledged = sum(1 for a in alerts if a.acknowledged)
    
    for alert in alerts:
        lvl = alert.level.value if hasattr(alert.level, "value") else str(alert.level)
        by_level[lvl] = by_level.get(lvl, 0) + 1
        atp = alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type)
        by_type[atp] = by_type.get(atp, 0) + 1
        
        # По корпусам
        if alert.housing_id:
            if alert.housing_id not in by_housing:
                by_housing[alert.housing_id] = {
                    "total": 0,
                    "critical": 0,
                    "warning": 0,
                    "info": 0
                }
            
            by_housing[alert.housing_id]["total"] += 1
            if lvl == AlertLevel.CRITICAL.value or lvl == "critical":
                by_housing[alert.housing_id]["critical"] += 1
            elif lvl == AlertLevel.WARNING.value or lvl == "warning":
                by_housing[alert.housing_id]["warning"] += 1
            else:
                by_housing[alert.housing_id]["info"] += 1
    
    # Получаем названия корпусов
    housing_details = {}
    if by_housing:
        housing_ids = list(by_housing.keys())
        housing_result = await db.execute(
            select(Housing).where(Housing.id.in_(housing_ids))
        )
        housings = housing_result.scalars().all()
        for housing in housings:
            housing_details[housing.id] = housing.name
    
    return {
        "period": {
            "from": date_from,
            "to": date_to
        },
        "total_alerts": total,
        "acknowledged_alerts": acknowledged,
        "acknowledgment_rate": acknowledged / total if total > 0 else 0,
        "by_level": by_level,
        "by_type": by_type,
        "by_housing": {
            housing_details.get(hid, str(hid)): data
            for hid, data in by_housing.items()
        },
        "escalated_alerts": sum(1 for a in alerts if a.escalation_level > 1),
        "avg_response_time_hours": 0  # В реальном приложении нужно рассчитывать
    }