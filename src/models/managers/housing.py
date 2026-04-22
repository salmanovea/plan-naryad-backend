from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.housing import Floor, Housing, Section
from src.models.managers.common import BaseManager


class HousingManager(BaseManager[Housing]):
    """Data access for Housing entities."""

    entity = Housing
    text_search_fields = {"name": "ilike", "complex_name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class SectionManager(BaseManager[Section]):
    """Data access for Section entities."""

    entity = Section
    text_search_fields = {"name": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)


class FloorManager(BaseManager[Floor]):
    """Data access for Floor entities."""

    entity = Floor

    def __init__(self, db: AsyncSession):
        super().__init__(db)
