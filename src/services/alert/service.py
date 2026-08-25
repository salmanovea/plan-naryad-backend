from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemes import PaginationParams
from src.api.v1.alert.schemes import AlertSchema
from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo.tables.alert import Alert, AlertLevel, AlertType
from src.models.dbo.tables.reconciliation import ReconciliationPattern, ReconciliationStatus
from src.services.common import BaseService

log = LoggerProvider().get_logger(__name__)

# Single source of truth for alert_type -> severity level (see spec-alerts.md §2).
# Used on generation so the level never drifts from the alert semantics and the
# frontend can mirror this table for labels/colors. A type missing from the map
# falls back to WARNING (never INFO) so an unmapped critical never looks benign.
ALERT_LEVEL_MAP: Dict[str, AlertLevel] = {
    AlertType.A01: AlertLevel.INFO,
    AlertType.A02: AlertLevel.WARNING,
    AlertType.A03: AlertLevel.INFO,
    AlertType.A04: AlertLevel.WARNING,
    AlertType.A05: AlertLevel.WARNING,
    AlertType.A06: AlertLevel.INFO,
    AlertType.A07: AlertLevel.CRITICAL,
    AlertType.A10: AlertLevel.CRITICAL,
    AlertType.A11: AlertLevel.CRITICAL,
    AlertType.A12: AlertLevel.WARNING,
    AlertType.A13: AlertLevel.CRITICAL,
    AlertType.A14: AlertLevel.WARNING,
    AlertType.A15: AlertLevel.CRITICAL,
    AlertType.A20: AlertLevel.CRITICAL,
    AlertType.A21: AlertLevel.CRITICAL,
    AlertType.A22: AlertLevel.WARNING,
    AlertType.A23: AlertLevel.WARNING,
}


def level_for_alert_type(alert_type: str) -> str:
    """Return the severity level for an alert type, defaulting to WARNING."""
    return ALERT_LEVEL_MAP.get(alert_type, AlertLevel.WARNING).value


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

    @staticmethod
    def _enrich_alert(alert: Alert) -> AlertSchema:
        """Map an alert (with relations loaded) to a schema with readable labels."""
        schema = AlertSchema.model_validate(alert)
        schema.housing_name = alert.housing.name if alert.housing else None
        schema.contractor_name = alert.contractor.name if alert.contractor else None
        return schema

    async def list_alerts(
        self,
        pagination: PaginationParams,
        order_by: List[str],
        **filters,
    ) -> Tuple[List[AlertSchema], int]:
        """List alerts with denormalized housing/contractor names."""
        query = self.alert_manager.get_enriched_query()
        items = await self.alert_manager.search(query=query, order_by=order_by, pagination=pagination, **filters)
        total = await self.alert_manager.count(**filters)
        return [self._enrich_alert(i) for i in items], total

    async def get_alert(self, alert_id: UUID) -> Optional[AlertSchema]:
        """Fetch a single alert with denormalized housing/contractor names."""
        alert = await self.alert_manager.get_enriched_by_id(alert_id)
        return self._enrich_alert(alert) if alert else None

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
            p.contractor_id for p in await self.plan_item_manager.search(housing_id=housing_id, date=alert_date)
        }
        submitted_contractors_ids = {
            f.contractor_id for f in await self.work_fact_manager.search(housing_id=housing_id, work_date=alert_date)
        }

        for contractor_id in planned_contractors_ids:
            if contractor_id not in submitted_contractors_ids:
                contractor = await self.contractor_manager.get_by_id(contractor_id)
                if contractor:
                    alerts.append(
                        {
                            "alert_type": "A05",
                            "level": level_for_alert_type("A05"),
                            "date": alert_date,
                            "housing_id": housing_id,
                            "contractor_id": contractor_id,
                            "recipient_role": "RS",
                            "message": f"Подрядчик «{contractor.name}» не подал факт за {alert_date}.",
                            "created_at": datetime.now(),
                        }
                    )

        housing = await self.housing_manager.get_by_id(housing_id)
        if housing:
            alerts.append(
                {
                    "alert_type": "A06",
                    "level": level_for_alert_type("A06"),
                    "date": alert_date,
                    "housing_id": housing_id,
                    "recipient_role": "RS",
                    "message": f"Сводка за {alert_date} по объекту «{housing.name}» готова.",
                    "created_at": datetime.now(),
                }
            )

        return alerts

    async def _reconciliation_alerts_data(self, housing_id: UUID, alert_date: date) -> List[Dict]:
        alerts = []

        recon_items = await self.reconciliation_manager.search(
            date=alert_date,
            housing_id=housing_id,
            status__in=[ReconciliationStatus.NOT_DONE, ReconciliationStatus.DONE_PARTIAL],
        )

        critical_items = [
            item
            for item in recon_items
            if item.status == ReconciliationStatus.NOT_DONE
            or (
                item.status == ReconciliationStatus.DONE_PARTIAL
                and item.completion_ratio
                and item.completion_ratio < 0.5
            )
        ]

        if not critical_items:
            return []

        housing = await self.housing_manager.get_by_id(housing_id)
        by_contractor: Dict[UUID, List] = {}
        for item in critical_items:
            if item.contractor_id:
                by_contractor.setdefault(item.contractor_id, []).append(item)

        for contractor_id, items in by_contractor.items():
            contractor = await self.contractor_manager.get_by_id(contractor_id)
            if contractor and housing:
                alerts.append(
                    {
                        "alert_type": "A07",
                        "level": level_for_alert_type("A07"),
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
                    }
                )

        return alerts

    async def _pattern_alerts_data(self, housing_id: UUID, alert_date: date) -> List[Dict]:
        alerts = []

        pattern_items = await self.reconciliation_manager.search(
            date=alert_date,
            housing_id=housing_id,
            pattern__in=[ReconciliationPattern.WRONG_LOCATION, ReconciliationPattern.WRONG_WORK_TYPE],
        )

        for item in pattern_items:
            if not item.contractor_id:
                continue
            contractor = await self.contractor_manager.get_by_id(item.contractor_id)
            if contractor:
                pattern_text = "не там" if item.pattern == ReconciliationPattern.WRONG_LOCATION else "не та работа"
                alerts.append(
                    {
                        "alert_type": "A12",
                        "level": level_for_alert_type("A12"),
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
                    }
                )

        overdue_items: List[Dict] = []

        if overdue_items:
            housing = await self.housing_manager.get_by_id(housing_id)
            if housing:
                alerts.append(
                    {
                        "alert_type": "A15",
                        "level": level_for_alert_type("A15"),
                        "date": alert_date,
                        "housing_id": housing_id,
                        "recipient_role": "RS",
                        "message": (
                            f"Просрочка по календарному плану\n\n"
                            f"Объект: {housing.name}\n"
                            f"Просроченных работ: {len(overdue_items)}"
                        ),
                        "created_at": datetime.now(),
                    }
                )

        return alerts

    async def _system_alerts_data(self, housing_id: UUID, alert_date: date) -> List[Dict]:
        alerts = []

        has_tech = bool(await self.tech_sequence_manager.search(housing_id=housing_id))
        if not has_tech:
            housing = await self.housing_manager.get_by_id(housing_id)
            if housing:
                alerts.append(
                    {
                        "alert_type": "A22",
                        "level": level_for_alert_type("A22"),
                        "date": alert_date,
                        "housing_id": housing_id,
                        "recipient_role": "ADMIN",
                        "message": (
                            f"Нет техпоследовательности\n\n"
                            f"Для корпуса «{housing.name}» не задана техпоследовательность.\n"
                            f"Автогенерация план-наряда невозможна."
                        ),
                        "created_at": datetime.now(),
                    }
                )

        return alerts

    async def check_escalation(self, alert_id: UUID) -> bool:
        alert = await self.alert_manager.get_by_id(alert_id)
        if not alert or alert.acknowledged:
            return False

        hours_since = (datetime.now() - alert.created_at).total_seconds() / 3600
        rules = ESCALATION_RULES.get(alert.alert_type, [])

        for i, (hours_needed, next_role) in enumerate(rules):
            # escalation_level starts at 1 (level 1 = initial recipient); step i
            # raises it to level i + 2. Apply a step only if the alert has not
            # already reached that level — note the default level is 1, not 0.
            if hours_since >= hours_needed and alert.escalation_level <= i + 1:
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
                # escalation_level starts at 1; step i raises it to level i + 2.
                # Skip steps already applied (default level is 1, not 0).
                if hours_since >= hours_needed and alert.escalation_level <= i + 1:
                    alert.escalation_level = i + 2
                    alert.escalated_at = now
                    alert.recipient_role = next_role
                    escalated += 1
                    break

        if escalated:
            await self.alert_manager.db.commit()

        return escalated

    async def acknowledge_alert(self, alert_id: UUID, user_id: str) -> Optional[Alert]:
        alert = await self.alert_manager.get_by_id(alert_id)
        if alert:
            await self.alert_manager.update_by_id(
                alert_id,
                {
                    "acknowledged": True,
                    "acknowledged_at": datetime.now(),
                    "acknowledged_by": user_id,
                },
            )
            log.info(f"Alert {alert_id} acknowledged by {user_id}")
        return alert


async def get_alert_service(db: AsyncSession = Depends(get_session)) -> AlertService:
    return AlertService(db=db)
