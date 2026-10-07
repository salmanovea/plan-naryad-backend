"""Bodies of the scheduled work: facts first, then the plan; hand-over at the cutoff.

The endpoints in `src/api/v1/task/views.py` are thin wrappers over this service — Raport's
taskiq hits them on its schedule. Any future caller without HTTP around it (an own scheduler,
a CLI) talks to this service directly; there is deliberately no other entry point to keep in
sync.

Each housing runs as its own unit of work on the shared session: commit on success, rollback
on failure. One broken housing — Raport timing out, no calendar plan, a connection Postgres
killed — must not cost the others their plan, and the caller gets a per-housing breakdown so
a partial failure is visible in Raport's job log rather than silent.
"""

from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import AsyncIterator, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.logger import LoggerProvider
from src.config.postgres.db_config import get_session
from src.models import managers
from src.services.common import BaseService
from src.services.plan.service import AutogenerationService, default_target_date
from src.services.sync.service import SyncReportService
from src.utils.business_time import business_today

log = LoggerProvider().get_logger(__name__)

SCHEDULER_ACTOR = "scheduler"


class TaskService(BaseService):
    """Orchestrates the two spec-mandated jobs over the plan and sync services."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @asynccontextmanager
    async def _step(self, entry: dict, name: str, raport_id: str) -> AsyncIterator[None]:
        """One unit of work on the shared session: commit on success, roll back on failure.

        The run shares one session across every housing, so a failure has to leave it usable
        for the next one. Without the rollback a dead connection — Postgres killing a backend
        that sat idle in transaction — poisons the session, and every housing after it fails
        with «Can't reconnect until invalid transaction is rolled back». The error is recorded
        on the housing's entry instead of raised: one broken housing must not stop the rest.
        """
        try:
            yield
            await self.db.commit()
        except Exception as err:
            await self.db.rollback()
            entry["errors"].append(f"{name}: {err}")
            log.error("nightly: %s failed for housing %s: %s", name, raport_id, err)

    async def housings_with_sequence(self) -> list[tuple[UUID, str]]:
        """(local id, raport id) for housings that have a technological sequence.

        A housing without one cannot be generated for: the spec wants an explicit «календарный
        план не сформирован» error there, not a nightly retry.
        """
        rows = await managers.TechSequenceItemManager(self.db).search()
        housing_ids = {row.housing_id for row in rows}
        if not housing_ids:
            return []
        housings = await managers.HousingManager(self.db).get_by_ids(list(housing_ids))
        return [(h.id, h.raport_id) for h in housings if h.raport_id]

    async def run_nightly_plan(
        self,
        target_date: Optional[date] = None,
        housing_raport_id: Optional[str] = None,
        actor: str = SCHEDULER_ACTOR,
    ) -> dict:
        """Facts first, then the day's plan, for one housing or all of them.

        `target_date` defaults to the rule from Р3 — today for a night run, tomorrow once the
        cutoff has passed.
        """
        target = target_date or default_target_date()
        yesterday = target - timedelta(days=1)

        if housing_raport_id:
            housings = await managers.HousingManager(self.db).search(raport_id=housing_raport_id)
            scope = [(h.id, h.raport_id) for h in housings if h.raport_id]
        else:
            scope = await self.housings_with_sequence()

        log.info("nightly: %d housing(s), target date %s", len(scope), target)
        per_housing: list[dict] = []
        totals = {"housings": len(scope), "facts": 0, "positions": 0, "failed": 0}

        for local_id, raport_id in scope:
            entry: dict = {"housing_id": str(local_id), "facts": 0, "positions": 0, "errors": []}

            async with self._step(entry, "sync_work_facts", raport_id):
                facts = await SyncReportService(self.db).sync_work_facts(raport_id, date_from=yesterday, date_to=target)
                entry["facts"] = facts.get("work_facts", 0)
                totals["facts"] += entry["facts"]

            async with self._step(entry, "generate_daily_plan", raport_id):
                items, reasons = await AutogenerationService(self.db).generate_daily_plan(
                    housing_id=local_id,
                    target_date=target,
                    force=False,
                    actor=actor,
                )
                entry["positions"] = len(items)
                totals["positions"] += entry["positions"]
                if reasons:
                    entry["reasons"] = reasons[:3]
                    log.warning("nightly: housing %s generated nothing — %s", local_id, reasons[:2])

            if entry["errors"]:
                totals["failed"] += 1
            per_housing.append(entry)

        log.info("nightly: done — %s", totals)
        return {"date": target, **totals, "housings_detail": per_housing}

    async def run_transfer(self, target_date: Optional[date] = None) -> dict:
        """Hand the day's positions over. Defaults to today — the cutoff job wants no arguments."""
        day = target_date or business_today()
        result = await AutogenerationService(self.db).transfer_day(day)
        log.info("transfer: %s for %s", result, day)
        return {"date": day, **result}


async def get_task_service(db: AsyncSession = Depends(get_session)) -> TaskService:
    return TaskService(db=db)
