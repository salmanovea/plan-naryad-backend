"""
Движок алертов и нотификаций.
Генерирует алерты на основе данных сверки, таймаутов и пороговых значений.
"""
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.plan import PlanItem
from app.models.fact import WorkFact as FactItem
from app.models.reconciliation import ReconciliationResult as ReconciliationItem, DailySummary
from app.models.contractor import Contractor
from app.models.housing import Housing
from app.models.work import TechSequenceItem
from app.schemas.alert import AlertCreate, AlertUpdate

logger = logging.getLogger(__name__)


class AlertEngine:
    """Движок генерации и управления алертами."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def generate_daily_alerts(self, housing_id: UUID, alert_date: date) -> List[Alert]:
        """
        Генерирует все алерты за день для указанного корпуса.
        Запускается после сверки (20:30).
        """
        logger.info(f"Generating daily alerts for housing {housing_id}, date {alert_date}")
        alerts = []
        
        # 1. Operational alerts
        alerts.extend(await self._generate_operational_alerts(housing_id, alert_date))
        
        # 2. Reconciliation-based alerts
        alerts.extend(await self._generate_reconciliation_alerts(housing_id, alert_date))
        
        # 3. Pattern-based alerts (analytical)
        alerts.extend(await self._generate_pattern_alerts(housing_id, alert_date))
        
        # 4. System alerts
        alerts.extend(await self._generate_system_alerts(housing_id, alert_date))
        
        # Save all alerts
        for alert in alerts:
            self.db.add(alert)
        
        await self.db.commit()
        logger.info(f"Generated {len(alerts)} alerts")
        return alerts
    
    async def _generate_operational_alerts(self, housing_id: UUID, alert_date: date) -> List[Alert]:
        """Операционные алерты (A01-A06)."""
        alerts = []
        
        # A01: Plan generated (06:01) - This would be triggered by cron, not here
        # A02: RS didn't confirm plan (10:00) - triggered by cron
        # A03: Plan sent to contractor - triggered by cron
        # A04: Reminder to submit fact (18:00) - triggered by cron
        # A05: Contractor didn't submit fact (20:01) - check after reconciliation
        # A06: Daily summary ready (20:30) - generated after reconciliation
        
        # A05: Contractor didn't submit fact
        plans_stmt = (
            select(PlanItem.contractor_id)
            .where(PlanItem.date == alert_date)
            .where(PlanItem.housing_id == housing_id)
            .distinct()
        )
        planned_contractors_result = await self.db.execute(plans_stmt)
        planned_contractors = [row[0] for row in planned_contractors_result]
        
        facts_stmt = (
            select(FactItem.contractor_id)
            .where(FactItem.date == alert_date)
            .where(FactItem.housing_id == housing_id)
            .distinct()
        )
        submitted_contractors_result = await self.db.execute(facts_stmt)
        submitted_contractors = [row[0] for row in submitted_contractors_result]
        
        for contractor_id in planned_contractors:
            if contractor_id not in submitted_contractors:
                # Contractor didn't submit any facts
                contractor_stmt = select(Contractor).where(Contractor.id == contractor_id)
                contractor_result = await self.db.execute(contractor_stmt)
                contractor = contractor_result.scalar_one_or_none()
                
                if contractor:
                    alert = Alert(
                        alert_type="A05",
                        level="warning",
                        date=alert_date,
                        housing_id=housing_id,
                        contractor_id=contractor_id,
                        recipient_role="RS",  # RS gets this first
                        message=f"Подрядчик «{contractor.name}» не подал факт за {alert_date}.",
                        created_at=datetime.now()
                    )
                    alerts.append(alert)
        
        # A06: Daily summary ready
        housing_stmt = select(Housing).where(Housing.id == housing_id)
        housing_result = await self.db.execute(housing_stmt)
        housing = housing_result.scalar_one_or_none()
        
        if housing:
            summary_alert = Alert(
                alert_type="A06",
                level="info",
                date=alert_date,
                housing_id=housing_id,
                recipient_role="RS",
                message=f"Сводка за {alert_date} по объекту «{housing.name}» готова.",
                created_at=datetime.now()
            )
            alerts.append(summary_alert)
        
        return alerts
    
    async def _generate_reconciliation_alerts(self, housing_id: UUID, alert_date: date) -> List[Alert]:
        """Алерты на основе результатов сверки (A07)."""
        alerts = []
        
        # Get reconciliation results for critical deviations
        recon_stmt = (
            select(ReconciliationItem)
            .where(ReconciliationItem.date == alert_date)
            .where(ReconciliationItem.housing_id == housing_id)
            .where(ReconciliationItem.status.in_(["NOT_DONE", "DONE_PARTIAL"]))
        )
        recon_result = await self.db.execute(recon_stmt)
        recon_items = recon_result.scalars().all()
        
        critical_items = []
        for item in recon_items:
            if item.status == "NOT_DONE":
                critical_items.append(item)
            elif item.status == "DONE_PARTIAL":
                # Check if completion < 50%
                if item.completion_ratio and item.completion_ratio < 0.5:
                    critical_items.append(item)
        
        if critical_items:
            # Group by contractor
            by_contractor: Dict[UUID, List[ReconciliationItem]] = {}
            for item in critical_items:
                by_contractor.setdefault(item.contractor_id, []).append(item)
            
            housing_stmt = select(Housing).where(Housing.id == housing_id)
            housing_result = await self.db.execute(housing_stmt)
            housing = housing_result.scalar_one_or_none()
            
            for contractor_id, items in by_contractor.items():
                contractor_stmt = select(Contractor).where(Contractor.id == contractor_id)
                contractor_result = await self.db.execute(contractor_stmt)
                contractor = contractor_result.scalar_one_or_none()
                
                if contractor and housing:
                    alert = Alert(
                        alert_type="A07",
                        level="critical",
                        date=alert_date,
                        housing_id=housing_id,
                        contractor_id=contractor_id,
                        recipient_role="DS",  # Direct to DS/DP
                        message=(
                            f"🚨 Критическое отклонение\n\n"
                            f"Объект: {housing.name}\n"
                            f"Дата: {alert_date}\n"
                            f"Подрядчик: {contractor.name}\n\n"
                            f"Критических отклонений: {len(items)}\n"
                            f"Пример: {items[0].status} (выполнение: {items[0].completion_ratio*100:.0f}%)"
                        ),
                        created_at=datetime.now()
                    )
                    alerts.append(alert)
        
        return alerts
    
    async def _generate_pattern_alerts(self, housing_id: UUID, alert_date: date) -> List[Alert]:
        """Аналитические алерты по паттернам (A10-A15)."""
        alerts = []
        
        # A10: Chronic underperformance (3+ days with completion < 50%)
        # A11: Chronic no-report (3+ days NO_REPORT)
        # A12: Work not according to plan (WRONG_LOCATION/WRONG_WORK_TYPE)
        # A13: RS not managing (3+ days without plan confirmation)
        # A14: High RS deviation from standard (>30% per week)
        # A15: Calendar plan overdue
        
        # For now, implement A12: Wrong location/work type
        recon_stmt = (
            select(ReconciliationItem)
            .where(ReconciliationItem.date == alert_date)
            .where(ReconciliationItem.housing_id == housing_id)
            .where(ReconciliationItem.pattern.in_(["WRONG_LOCATION", "WRONG_WORK_TYPE"]))
        )
        recon_result = await self.db.execute(recon_stmt)
        pattern_items = recon_result.scalars().all()
        
        for item in pattern_items:
            contractor_stmt = select(Contractor).where(Contractor.id == item.contractor_id)
            contractor_result = await self.db.execute(contractor_stmt)
            contractor = contractor_result.scalar_one_or_none()
            
            if contractor:
                pattern_text = "не там" if item.pattern == "WRONG_LOCATION" else "не та работа"
                alert = Alert(
                    alert_type="A12",
                    level="warning",
                    date=alert_date,
                    housing_id=housing_id,
                    contractor_id=item.contractor_id,
                    recipient_role="RS",
                    message=(
                        f"⚠️ Работа не по плану\n\n"
                        f"Подрядчик «{contractor.name}» выполнил работу {pattern_text}.\n"
                        f"Дата: {alert_date}\n"
                        f"Проверьте выполнение на объекте."
                    ),
                    created_at=datetime.now()
                )
                alerts.append(alert)
        
        # A15: Calendar plan overdue
        # Check tech sequence items with planned_end < today and not done
        today = date.today()
        tech_stmt = (
            select(TechSequenceItem)
            .where(TechSequenceItem.planned_end < today)
            .where(TechSequenceItem.housing_id == housing_id)
            .where(TechSequenceItem.status != 'done')
        )
        tech_result = await self.db.execute(tech_stmt)
        overdue_items = tech_result.scalars().all()
        
        if overdue_items:
            housing_stmt = select(Housing).where(Housing.id == housing_id)
            housing_result = await self.db.execute(housing_stmt)
            housing = housing_result.scalar_one_or_none()
            
            if housing:
                alert = Alert(
                    alert_type="A15",
                    level="critical",
                    date=alert_date,
                    housing_id=housing_id,
                    recipient_role="RS",
                    message=(
                        f"📅 Просрочка по календарному плану\n\n"
                        f"Объект: {housing.name}\n"
                        f"Просроченных работ: {len(overdue_items)}\n"
                        f"Пример: {overdue_items[0].work_name}"
                    ),
                    created_at=datetime.now()
                )
                alerts.append(alert)
        
        return alerts
    
    async def _generate_system_alerts(self, housing_id: UUID, alert_date: date) -> List[Alert]:
        """Системные алерты (A20-A23)."""
        alerts = []
        
        # A20: Generation didn't run (cron 06:00) - checked by cron
        # A21: Reconciliation didn't run (cron 20:00) - checked by cron
        # A22: No tech sequence for housing
        tech_stmt = select(TechSequenceItem).where(TechSequenceItem.housing_id == housing_id).limit(1)
        tech_result = await self.db.execute(tech_stmt)
        has_tech_seq = tech_result.scalar_one_or_none() is not None
        
        if not has_tech_seq:
            housing_stmt = select(Housing).where(Housing.id == housing_id)
            housing_result = await self.db.execute(housing_stmt)
            housing = housing_result.scalar_one_or_none()
            
            if housing:
                alert = Alert(
                    alert_type="A22",
                    level="warning",
                    date=alert_date,
                    housing_id=housing_id,
                    recipient_role="ADMIN",
                    message=(
                        f"⚠️ Нет техпоследовательности\n\n"
                        f"Для корпуса «{housing.name}» не задана техпоследовательность.\n"
                        f"Автогенерация план-наряда невозможна."
                    ),
                    created_at=datetime.now()
                )
                alerts.append(alert)
        
        # A23: Contractor not assigned to work type
        # Check if there are work types without assigned contractors
        # Implementation depends on specific data model
        
        return alerts
    
    async def check_escalation(self, alert: Alert) -> bool:
        """
        Проверяет, нужна ли эскалация алерта.
        Returns True if alert was escalated.
        """
        if alert.acknowledged:
            return False
        
        hours_since = (datetime.now() - alert.created_at).total_seconds() / 3600
        
        # Escalation rules based on alert type
        escalation_rules = {
            "A02": [(4, "DS"), (8, "DP")],      # RS didn't confirm: RS→DS→DP
            "A05": [(8, "DS")],                 # No fact: RS→DS
            "A07": [(24, "DP")],                # Critical: DS→DP
            "A10": [(24, "DS"), (48, "DP")],    # Chronic: RS→DS→DP
            "A15": [(24, "DS"), (48, "DP")],    # Overdue: RS→DS→DP
        }
        
        rules = escalation_rules.get(alert.alert_type, [])
        
        for hours_needed, next_role in rules:
            if hours_since >= hours_needed and alert.escalation_level < len(rules):
                # Escalate
                alert.escalation_level += 1
                alert.escalated_at = datetime.now()
                alert.recipient_role = next_role
                
                escalation_msg = {
                    "DS": "Департамент строительства",
                    "DP": "Департамент проектирования"
                }.get(next_role, next_role)
                
                alert.message = f"⬆️ Эскалация ({escalation_msg})\n\n{alert.message}"
                
                await self.db.commit()
                logger.info(f"Alert {alert.id} escalated to {next_role}")
                return True
        
        return False
    
    async def acknowledge_alert(self, alert_id: UUID, user_id: UUID) -> Optional[Alert]:
        """Отмечает алерт как подтверждённый."""
        stmt = select(Alert).where(Alert.id == alert_id)
        result = await self.db.execute(stmt)
        alert = result.scalar_one_or_none()
        
        if alert:
            alert.acknowledged = True
            alert.acknowledged_at = datetime.now()
            alert.acknowledged_by = user_id
            await self.db.commit()
            logger.info(f"Alert {alert_id} acknowledged by user {user_id}")
        
        return alert


async def generate_alerts_for_housing(db: AsyncSession, housing_id: UUID, alert_date: date) -> List[Alert]:
    """Публичная функция для генерации алертов."""
    engine = AlertEngine(db)
    return await engine.generate_daily_alerts(housing_id, alert_date)