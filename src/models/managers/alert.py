from typing import Optional
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemes import PaginationParams
from src.models.dbo.tables.alert import Alert
from src.models.dbo.tables.contractor import Contractor
from src.models.dbo.tables.housing import Housing
from src.models.managers.common import BaseManager
from src.utils.helpers import get_paginated_query


class AlertManager(BaseManager[Alert]):
    """Data access for Alert entities."""

    entity = Alert
    text_search_fields = {"message": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def get_enriched_query(self) -> Select:
        """Base query eager-loading housing/contractor for label denormalization."""
        return select(Alert).options(
            selectinload(Alert.housing),
            selectinload(Alert.contractor),
        )

    async def get_enriched_by_id(self, alert_id: UUID) -> Optional[Alert]:
        """Fetch a single alert by id with housing/contractor eager-loaded."""
        query = self.get_enriched_query().where(Alert.id == alert_id)
        rows = await self.fetch(query)
        return rows[0] if rows else None
