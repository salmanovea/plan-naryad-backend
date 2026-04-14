"""
Логика эскалации алертов.
Интегрирована в AlertEngine (services/alerts.py).
Этот модуль — для будущего расширения (cron-задачи, webhook'и).
"""
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert

logger = logging.getLogger(__name__)

# Правила эскалации: alert_type → [(часов_до_эскалации, роль)]
ESCALATION_RULES = {
    "A02": [(4, "DS"), (8, "DP")],
    "A05": [(8, "DS")],
    "A07": [(24, "DP")],
    "A10": [(24, "DS"), (48, "DP")],
    "A11": [(24, "DS"), (48, "DP")],
    "A15": [(24, "DS"), (48, "DP")],
}


async def run_escalation_check(db: AsyncSession) -> int:
    """
    Проверяет все неподтверждённые алерты и эскалирует при необходимости.
    Запускается периодически (каждый час).
    Returns: количество эскалированных алертов.
    """
    stmt = select(Alert).where(Alert.acknowledged == False)
    result = await db.execute(stmt)
    unacked = result.scalars().all()
    
    escalated = 0
    now = datetime.now()
    
    for alert in unacked:
        rules = ESCALATION_RULES.get(alert.alert_type, [])
        if not rules:
            continue
        
        hours_since = (now - alert.created_at).total_seconds() / 3600
        
        for i, (hours_needed, next_role) in enumerate(rules):
            if hours_since >= hours_needed and alert.escalation_level <= i:
                alert.escalation_level = i + 2
                alert.escalated_at = now
                alert.recipient_role = next_role
                escalated += 1
                logger.info(f"Alert {alert.id} escalated to {next_role}")
                break
    
    if escalated:
        await db.commit()
    
    return escalated