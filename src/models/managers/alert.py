from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def search_with_names(
        self,
        order_by: Optional[list[str]] = None,
        pagination: Optional[PaginationParams] = None,
        **filters,
    ) -> list[Alert]:
        """Search alerts and attach joined housing_name / contractor_name labels."""
        stmt = (
            select(
                Alert,
                Housing.name.label("housing_name"),
                Contractor.name.label("contractor_name"),
            )
            .outerjoin(Housing, Alert.housing_id == Housing.id)
            .outerjoin(Contractor, Alert.contractor_id == Contractor.id)
        )
        stmt = self.apply_filters(stmt, **filters)
        if order_by:
            stmt = self.apply_ordering(stmt, order_by)
        if pagination:
            stmt = get_paginated_query(stmt, pagination)

        result = await self.db.execute(stmt)
        items: list[Alert] = []
        for alert, housing_name, contractor_name in result.all():
            alert.housing_name = housing_name
            alert.contractor_name = contractor_name
            items.append(alert)
        return items
