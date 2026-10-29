from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo import models as m
from src.services.access.service import AccessService
from src.services.common import BaseService


class WorkService(BaseService):
    def __init__(self, db: AsyncSession):
        self.access = AccessService(db)
        self.work_set_manager = managers.WorkSetManager(db)
        self.work_group_manager = managers.WorkGroupManager(db)
        self.work_type_manager = managers.WorkTypeManager(db)
        self.work_manager = managers.WorkManager(db)
        self.tech_sequence_manager = managers.TechSequenceItemManager(db)
        self.housing_manager = managers.HousingManager(db)

    async def _authorize_selectors(self, filters: dict[str, Any]) -> None:
        if housing_id := filters.get("housing_id"):
            await self.access.require_location(housing_id, filters.get("section_id"))
        elif section_id := filters.get("section_id"):
            await self.access.require_sections([section_id])

    async def search_work_set(self, **filters: Any) -> list[m.WorkSet]:
        """List work_set using the operation's explicit assignment filter."""
        return await self.work_set_manager.search(**filters)

    async def count_work_set(self, **filters: Any) -> int:
        """Count the same records available to the work_set list."""
        return await self.work_set_manager.count(**filters)

    async def get_work_set(self, entity_id: UUID) -> m.WorkSet | None:
        """Authorize a selected work_set before resolving its identity."""
        return await self.work_set_manager.get_by_id(entity_id)

    async def create_work_set(self, payload: dict[str, Any]) -> m.WorkSet:
        """Create work_set after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.work_set_manager.create(payload)

    async def update_work_set(self, entity_id: UUID, payload: dict[str, Any]) -> m.WorkSet | None:
        """Update an authorized work_set."""
        self.access.require_shared_write()
        return await self.work_set_manager.update_by_id(entity_id, payload)

    async def delete_work_set(self, entity_id: UUID) -> None:
        """Delete an authorized work_set."""
        self.access.require_shared_write()
        await self.work_set_manager.delete_by_id(entity_id)

    async def search_work_group(self, **filters: Any) -> list[m.WorkGroup]:
        """List work_group using the operation's explicit assignment filter."""
        return await self.work_group_manager.search(**filters)

    async def count_work_group(self, **filters: Any) -> int:
        """Count the same records available to the work_group list."""
        return await self.work_group_manager.count(**filters)

    async def get_work_group(self, entity_id: UUID) -> m.WorkGroup | None:
        """Authorize a selected work_group before resolving its identity."""
        return await self.work_group_manager.get_by_id(entity_id)

    async def create_work_group(self, payload: dict[str, Any]) -> m.WorkGroup:
        """Create work_group after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.work_group_manager.create(payload)

    async def update_work_group(self, entity_id: UUID, payload: dict[str, Any]) -> m.WorkGroup | None:
        """Update an authorized work_group."""
        self.access.require_shared_write()
        return await self.work_group_manager.update_by_id(entity_id, payload)

    async def delete_work_group(self, entity_id: UUID) -> None:
        """Delete an authorized work_group."""
        self.access.require_shared_write()
        await self.work_group_manager.delete_by_id(entity_id)

    async def search_work_type(self, **filters: Any) -> list[m.WorkType]:
        """List work_type using the operation's explicit assignment filter."""
        return await self.work_type_manager.search(**filters)

    async def count_work_type(self, **filters: Any) -> int:
        """Count the same records available to the work_type list."""
        return await self.work_type_manager.count(**filters)

    async def get_work_type(self, entity_id: UUID) -> m.WorkType | None:
        """Authorize a selected work_type before resolving its identity."""
        return await self.work_type_manager.get_by_id(entity_id)

    async def create_work_type(self, payload: dict[str, Any]) -> m.WorkType:
        """Create work_type after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.work_type_manager.create(payload)

    async def update_work_type(self, entity_id: UUID, payload: dict[str, Any]) -> m.WorkType | None:
        """Update an authorized work_type."""
        self.access.require_shared_write()
        return await self.work_type_manager.update_by_id(entity_id, payload)

    async def delete_work_type(self, entity_id: UUID) -> None:
        """Delete an authorized work_type."""
        self.access.require_shared_write()
        await self.work_type_manager.delete_by_id(entity_id)

    async def search_work(self, **filters: Any) -> list[m.Work]:
        """List work using the operation's explicit assignment filter."""
        return await self.work_manager.search(**filters)

    async def count_work(self, **filters: Any) -> int:
        """Count the same records available to the work list."""
        return await self.work_manager.count(**filters)

    async def get_work(self, entity_id: UUID) -> m.Work | None:
        """Authorize a selected work before resolving its identity."""
        return await self.work_manager.get_by_id(entity_id)

    async def create_work(self, payload: dict[str, Any]) -> m.Work:
        """Create work after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.work_manager.create(payload)

    async def update_work(self, entity_id: UUID, payload: dict[str, Any]) -> m.Work | None:
        """Update an authorized work."""
        self.access.require_shared_write()
        return await self.work_manager.update_by_id(entity_id, payload)

    async def delete_work(self, entity_id: UUID) -> None:
        """Delete an authorized work."""
        self.access.require_shared_write()
        await self.work_manager.delete_by_id(entity_id)

    async def search_tech_sequence(self, **filters: Any) -> list[m.TechSequenceItem]:
        """List tech_sequence using the operation's explicit assignment filter."""
        await self._authorize_selectors(filters)
        allowed_ids = self.access.tech_sequence_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        query = self.tech_sequence_manager.get_enriched_query()
        return await self.tech_sequence_manager.search(query=query, **filters)

    async def create_tech_sequence(self, payload: dict[str, Any]) -> m.TechSequenceItem:
        """Create tech_sequence after validating its declared parent references."""
        self.access.require_business_write()
        await self._authorize_selectors(payload)
        return await self.tech_sequence_manager.create(payload)

    async def delete_tech_sequence(self, entity_id: UUID) -> None:
        """Delete an authorized tech_sequence."""
        self.access.require_business_write()
        await self.access.require_tech_sequences([entity_id])
        await self.tech_sequence_manager.delete_by_id(entity_id)

    async def get_housing(self, entity_id: UUID) -> m.Housing | None:
        """Authorize a selected housing before resolving its identity."""
        await self.access.require_housings([entity_id])
        return await self.housing_manager.get_by_id(entity_id)


async def get_work_service(db: AsyncSession = Depends(get_session)) -> WorkService:
    return WorkService(db=db)
