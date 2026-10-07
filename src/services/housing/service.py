from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo import models as m
from src.services.access.service import AccessService
from src.services.common import BaseService


class HousingService(BaseService):
    def __init__(self, db: AsyncSession):
        self.access = AccessService(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.construction_object_manager = managers.ConstructionObjectManager(db)
        self.queue_manager = managers.QueueManager(db)

    async def _authorize_selectors(self, filters: dict[str, Any]) -> None:
        """Authorize parents declared by section and floor operations."""
        if housing_id := filters.get("housing_id"):
            await self.access.require_housings([housing_id])
        if section_id := filters.get("section_id"):
            await self.access.require_sections([section_id])

    async def construction_object_ids_of_project(self, project_id: UUID) -> list[UUID]:
        """Construction objects of a project — `project_id` filters through them."""
        await self.access.require_projects([project_id])
        objects = await self.construction_object_manager.search(project_id=project_id, id__in=self.access.object_ids())
        return [o.id for o in objects]

    async def with_queue(self, housings: list) -> list[dict]:
        """Attach project and queue to each housing.

        The spec wants the housing filter shown as «Очередь → Корпус», and the project filter
        alongside it. Resolving that on the client would mean three requests and a join per
        dropdown, so the chain housing → construction object → queue is walked here once.
        """
        if not housings:
            return []

        object_ids = {h.construction_object_id for h in housings if h.construction_object_id}
        objects = (
            {o.id: o for o in await self.construction_object_manager.get_by_ids(list(object_ids))} if object_ids else {}
        )
        queue_ids = {o.queue_id for o in objects.values() if o.queue_id}
        queues = {q.id: q for q in await self.queue_manager.get_by_ids(list(queue_ids))} if queue_ids else {}

        rows: list[dict] = []
        for housing in housings:
            obj = objects.get(housing.construction_object_id) if housing.construction_object_id else None
            queue = queues.get(obj.queue_id) if obj and obj.queue_id else None
            rows.append(
                {
                    **{key: getattr(housing, key) for key in ("id", "name", "complex_name", "description")},
                    "construction_object_id": housing.construction_object_id,
                    "project_id": obj.project_id if obj else None,
                    "queue_id": queue.id if queue else None,
                    "queue_name": queue.name if queue else None,
                }
            )
        return rows

    async def search_housing(self, **filters: Any) -> list[m.Housing]:
        """List housing using the operation's explicit assignment filter."""
        if object_id := filters.get("construction_object_id"):
            await self.access.require_objects([object_id])
        allowed_ids = self.access.housing_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.housing_manager.search(**filters)

    async def count_housing(self, **filters: Any) -> int:
        """Count the same records available to the housing list."""
        if object_id := filters.get("construction_object_id"):
            await self.access.require_objects([object_id])
        allowed_ids = self.access.housing_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.housing_manager.count(**filters)

    async def get_housing(self, entity_id: UUID) -> m.Housing | None:
        """Authorize a selected housing before resolving its identity."""
        await self.access.require_housings([entity_id])
        return await self.housing_manager.get_by_id(entity_id)

    async def create_housing(self, payload: dict[str, Any]) -> m.Housing:
        """Create housing after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.housing_manager.create(payload)

    async def update_housing(self, entity_id: UUID, payload: dict[str, Any]) -> m.Housing | None:
        """Update an authorized housing."""
        self.access.require_business_write()
        await self.access.require_housings([entity_id])
        return await self.housing_manager.update_by_id(entity_id, payload)

    async def delete_housing(self, entity_id: UUID) -> None:
        """Delete an authorized housing."""
        self.access.require_business_write()
        await self.access.require_housings([entity_id])
        await self.housing_manager.delete_by_id(entity_id)

    async def search_section(self, **filters: Any) -> list[m.Section]:
        """List section using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.section_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.section_manager.search(**filters)

    async def create_section(self, payload: dict[str, Any]) -> m.Section:
        """Create section after validating its declared parent references."""
        self.access.require_business_write()
        await self._authorize_selectors(payload)
        return await self.section_manager.create(payload)

    async def update_section(self, entity_id: UUID, payload: dict[str, Any]) -> m.Section | None:
        """Update an authorized section."""
        self.access.require_business_write()
        await self.access.require_sections([entity_id])
        await self._authorize_selectors(payload)
        return await self.section_manager.update_by_id(entity_id, payload)

    async def delete_section(self, entity_id: UUID) -> None:
        """Delete an authorized section."""
        self.access.require_business_write()
        await self.access.require_sections([entity_id])
        await self.section_manager.delete_by_id(entity_id)

    async def search_floor(self, **filters: Any) -> list[m.Floor]:
        """List floor using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.floor_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.floor_manager.search(**filters)

    async def create_floor(self, payload: dict[str, Any]) -> m.Floor:
        """Create floor after validating its declared parent references."""
        self.access.require_business_write()
        await self._authorize_selectors(payload)
        return await self.floor_manager.create(payload)

    async def update_floor(self, entity_id: UUID, payload: dict[str, Any]) -> m.Floor | None:
        """Update an authorized floor."""
        self.access.require_business_write()
        await self.access.require_floors([entity_id])
        await self._authorize_selectors(payload)
        return await self.floor_manager.update_by_id(entity_id, payload)

    async def delete_floor(self, entity_id: UUID) -> None:
        """Delete an authorized floor."""
        self.access.require_business_write()
        await self.access.require_floors([entity_id])
        await self.floor_manager.delete_by_id(entity_id)


async def get_housing_service(db: AsyncSession = Depends(get_session)) -> HousingService:
    return HousingService(db=db)
