from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.models import managers
from src.models.dbo import models as m
from src.services.access.service import AccessService
from src.services.common import BaseService


class ContractorService(BaseService):
    def __init__(self, db: AsyncSession):
        self.access = AccessService(db)
        self.contractor_manager = managers.ContractorManager(db)

    async def search_contractor(self, **filters: Any) -> list[m.Contractor]:
        """List contractor using the operation's explicit assignment filter."""
        allowed_ids = self.access.contractor_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.contractor_manager.search(**filters)

    async def count_contractor(self, **filters: Any) -> int:
        """Count the same records available to the contractor list."""
        allowed_ids = self.access.contractor_ids()
        if allowed_ids is not None:
            filters["id__in"] = allowed_ids
        return await self.contractor_manager.count(**filters)

    async def get_contractor(self, entity_id: UUID) -> m.Contractor | None:
        """Authorize a selected contractor before resolving its identity."""
        await self.access.require_contractors([entity_id])
        return await self.contractor_manager.get_by_id(entity_id)

    async def create_contractor(self, payload: dict[str, Any]) -> m.Contractor:
        """Create contractor after validating its declared parent references."""
        self.access.require_shared_write()
        return await self.contractor_manager.create(payload)

    async def update_contractor(self, entity_id: UUID, payload: dict[str, Any]) -> m.Contractor | None:
        """Update an authorized contractor."""
        self.access.require_shared_write()
        await self.access.require_contractors([entity_id])
        return await self.contractor_manager.update_by_id(entity_id, payload)

    async def delete_contractor(self, entity_id: UUID) -> None:
        """Delete an authorized contractor."""
        self.access.require_shared_write()
        await self.access.require_contractors([entity_id])
        await self.contractor_manager.delete_by_id(entity_id)


async def get_contractor_service(db: AsyncSession = Depends(get_session)) -> ContractorService:
    return ContractorService(db=db)
