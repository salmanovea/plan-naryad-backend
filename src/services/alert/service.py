from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo.tables.reconciliation import ReconciliationPattern, ReconciliationStatus
from src.services.common import BaseService

log = LoggerProvider().get_logger(__name__)

ESCALATION_RULES: Dict[str, List] = {
    "A02": [(4, "DS"), (8, "DP")],
    "A05": [(8, "DS")],
    "A07": [(24, "DP")],
    "A10": [(24, "DS"), (48, "DP")],
    "A11": [(24, "DS"), (48, "DP")],
    "A15": [(24, "DS"), (48, "DP")],
}


class AlertService(BaseService):
    def __init__(self, db: AsyncSession):
        self.alert_manager = managers.AlertManager(db)
        self.plan_item_manager = managers.PlanItemManager(db)
        self.work_fact_manager = managers.WorkFactManager(db)
        self.reconciliation_manager = managers.ReconciliationResultManager(db)
        self.contractor_manager = managers.ContractorManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.tech_sequence_manager = managers.TechSequenceItemManager(db)

    async def generate_daily_alerts(self, housing_id: UUID, alert_date: date) -> List:
        log.info(f"Generating daily alerts for housing {housing_id}, date {alert_date}")
        alerts_data = []

        alerts_data.extend(await self._operational_alerts_data(housing_id, alert_date))
        alerts_data.extend(await self._reconciliation_alerts_data(housing_id, alert_date))
        alerts_data.extend(await self._pattern_alerts_data(housing_id, alert_date))
        alerts_data.extend(await self._system_alerts_data(housing_id, alert_date))

        created = []
        for data in alerts_data:
            alert = await self.alert_manager.create(data, commit=False)
            created.append(alert)

        if created:
            await self.alert_manager.db.commit()

        log.info(f"Generated {len(created)} alerts")
        return created

    async def _operational_alerts_data(self, housing_id: UUID, alert_date: date) -> List[Dict]:
        alerts = []

        planned_contractors_ids = {
            p.contractor_id
            for p in await self.plan_item_manager.search(housing_id=housing_id, date=alert_date)
        }
        submitted_contractors_ids = {
            f.contractor_id
            for f in await self.work_fact_manager.search(housing_id=housing_id, date=alert_date)
        }

        for contractor_id in planned_contractors_ids:
            if contractor_id not in submitted_contractors_ids:
                contractor = await self.contractor_manager.get_by_id(contractor_id)
                if contractor:
                    alerts.append({
                        "alert_type": "A05",
                        "level": "warning",
                        "date": alert_date,
                        "housing_id": housing_id,
                        "contractor_id": contractor_id,
                        "recipient_role": "RS",
                        "message": f"Подрядчик «{contractor.name}» не подал факт за {alert_date}.",
                        "created_at": datetime.now(),
                    })

        housing = await self.housing_manager.get_by_id(housing_id)
        if housing:
            alerts.append({
                "alert_type": "A06",
                "level": "info",
                "date": alert_date,
                "housing_id": housing_id,
                "recipient_role": "RS",
                "message": f"Сводка за {alert_date} по объекту «{housing.name}» готова.",
                "created_at": datetime.now(),
            })

        return alerts

    async def _reconciliation_alerts_data(self, housing_id: UUID, alert_date: date) -> List[Dict]:
        alerts = []

        recon_items = await self.reconciliation_manager.search(
            date=alert_date,
            housing_id=housing_id,
            status__in=[ReconciliationStatus.NOT_DONE, ReconciliationStatus.DONE_PARTIAL],
        )

        critical_items = [
            item for item in recon_items
            if item.status == ReconciliationStatus.NOT_DONE
            or (item.status == ReconciliationStatus.DONE_PARTIAL and item.completion_ratio and item.completion_ratio < 0.5)
        ]

        if not critical_items:
            return []

        housing = await self.housing_manager.get_by_id(housing_id)
        by_contractor: Dict[UUID, List] = {}
        for item in critical_items:
            by_contractor.setdefault(item.contractor_id, []).append(item)

        for contractor_id, items in by_contractor.items():
            contractor = await self.contractor_manager.get_by_id(contractor_id)
            if contractor and housing:
                alerts.append({
                    "alert_type": "A07",
                    "level": "critical",
                    "date": alert_date,
                    "housing_id": housing_id,
                    "contractor_id": contractor_id,
                    "recipient_role": "DS",
                    "message": (
                        f"Критическое отклонение\n\n"
                        f"Объект: {housing.name}\nДата: {alert_date}\n"
                        f"Подрядчик: {contractor.name}\n\n"
                        f"Критических отклонений: {len(items)}\n"
                        f"Пример: {items[0].status} (выполнение: {items[0].completion_ratio * 100:.0f}%)"
                    ),
                    "created_at": datetime.now(),
                })

        return alerts

    async def _pattern_alerts_data(self, housing_id: UUID, alert_date: date) -> List[Dict]:
        alerts = []

        pattern_items = await self.reconciliation_manager.search(
            date=alert_date,
            housing_id=housing_id,
            pattern__in=[ReconciliationPattern.WRONG_LOCATION, ReconciliationPattern.WRONG_WORK_TYPE],
        )

        for item in pattern_items:
            contractor = await self.contractor_manager.get_by_id(item.contractor_id)
            if contractor:
                pattern_text = "не там" if item.pattern == ReconciliationPattern.WRONG_LOCATION else "не та работа"
                alerts.append({
                    "alert_type": "A12",
                    "level": "warning",
                    "date": alert_date,
                    "housing_id": housing_id,
                    "contractor_id": item.contractor_id,
                    "recipient_role": "RS",
                    "message": (
                        f"Работа не по плану\n\n"
                        f"Подрядчик «{contractor.name}» выполнил работу {pattern_text}.\n"
                        f"Дата: {alert_date}"
                    ),
                    "created_at": datetime.now(),
                })

        today = date.today()
        overdue_items = await self.tech_sequence_manager.search(
            housing_id=housing_id,
            planned_end__lt=today,
            status__isnot="done",
        )

        if overdue_items:
            housing = await self.housing_manager.get_by_id(housing_id)
            if housing:
                alerts.append({
                    "alert_type": "A15",
                    "level": "critical",
                    "date": alert_date,
                    "housing_id": housing_id,
                    "recipient_role": "RS",
                    "message": (
                        f"Просрочка по календарному плану\n\n"
                        f"Объект: {housing.name}\n"
                        f"Просроченных работ: {len(overdue_items)}"
                    ),
                    "created_at": datetime.now(),
                })

        return alerts

    async def _system_alerts_data(self, housing_id: UUID, alert_date: date) -> List[Dict]:
        alerts = []

        has_tech = bool(await self.tech_sequence_manager.search(housing_id=housing_id))
        if not has_tech:
            housing = await self.housing_manager.get_by_id(housing_id)
            if housing:
                alerts.append({
                    "alert_type": "A22",
                    "level": "warning",
                    "date": alert_date,
                    "housing_id": housing_id,
                    "recipient_role": "ADMIN",
                    "message": (
                        f"Нет техпоследовательности\n\n"
                        f"Для корпуса «{housing.name}» не задана техпоследовательность.\n"
                        f"Автогенерация план-наряда невозможна."
                    ),
                    "created_at": datetime.now(),
                })

        return alerts

    async def check_escalation(self, alert_id: UUID) -> bool:
        alert = await self.alert_manager.get_by_id(alert_id)
        if not alert or alert.acknowledged:
            return False

        hours_since = (datetime.now() - alert.created_at).total_seconds() / 3600
        rules = ESCALATION_RULES.get(alert.alert_type, [])

        for i, (hours_needed, next_role) in enumerate(rules):
            if hours_since >= hours_needed and alert.escalation_level <= i:
                alert.escalation_level = i + 2
                alert.escalated_at = datetime.now()
                alert.recipient_role = next_role
                alert.message = f"Эскалация → {next_role}\n\n{alert.message}"
                await self.alert_manager.db.commit()
                log.info(f"Alert {alert_id} escalated to {next_role}")
                return True

        return False

    async def run_escalation_check(self) -> int:
        unacked = await self.alert_manager.search(acknowledged=False)
        escalated = 0
        now = datetime.now()

        for alert in unacked:
            rules = ESCALATION_RULES.get(alert.alert_type, [])
            hours_since = (now - alert.created_at).total_seconds() / 3600
            for i, (hours_needed, next_role) in enumerate(rules):
                if hours_since >= hours_needed and alert.escalation_level <= i:
                    alert.escalation_level = i + 2
                    alert.escalated_at = now
                    alert.recipient_role = next_role
                    escalated += 1
                    break

        if escalated:
            await self.alert_manager.db.commit()

        return escalated

    async def acknowledge_alert(self, alert_id: UUID, user_id: UUID) -> Optional:
        alert = await self.alert_manager.get_by_id(alert_id)
        if alert:
            await self.alert_manager.update_by_id(alert_id, {
                "acknowledged": True,
                "acknowledged_at": datetime.now(),
                "acknowledged_by": user_id,
            })
            log.info(f"Alert {alert_id} acknowledged by {user_id}")
        return alert


async def get_alert_service(db: AsyncSession = Depends(get_session)) -> AlertService:
    return AlertService(db=db)
