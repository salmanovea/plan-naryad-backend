from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo import models as m
from src.services.access.service import AccessService
from src.services.common import BaseService


class FactService(BaseService):
    def __init__(self, db: AsyncSession):
        self.access = AccessService(db)
        self.work_fact_manager = managers.WorkFactManager(db)

    async def _authorize_selectors(self, filters: dict[str, Any]) -> None:
        if housing_id := filters.get("housing_id"):
            await self.access.require_location(housing_id, filters.get("section_id"), filters.get("floor_id"))
        else:
            if section_id := filters.get("section_id"):
                await self.access.require_sections([section_id])
            if floor_id := filters.get("floor_id"):
                await self.access.require_floors([floor_id])
        if contractor_id := filters.get("contractor_id"):
            await self.access.require_contractors([contractor_id])

        if housing_ids := filters.get("housing_id__in"):
            await self.access.require_housings(housing_ids)
        if section_ids := filters.get("section_id__in"):
            await self.access.require_sections(section_ids)
        if floor_ids := filters.get("floor_id__in"):
            await self.access.require_floors(floor_ids)
        if contractor_ids := filters.get("contractor_id__in"):
            await self.access.require_contractors(contractor_ids)

    async def search_work_fact(self, **filters: Any) -> list[m.WorkFact]:
        """List work_fact using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.work_fact_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.work_fact_manager.search(**filters)

    async def count_work_fact(self, **filters: Any) -> int:
        """Count the same records available to the work_fact list."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.work_fact_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.work_fact_manager.count(**filters)

    async def get_work_fact(self, entity_id: UUID) -> m.WorkFact | None:
        """Authorize a selected work_fact before resolving its identity."""
        await self.access.require_work_facts([entity_id])
        return await self.work_fact_manager.get_by_id(entity_id)


async def get_fact_service(db: AsyncSession = Depends(get_session)) -> FactService:
    return FactService(db=db)
