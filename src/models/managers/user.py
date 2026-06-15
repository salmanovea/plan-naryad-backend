from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dbo.tables.user import User
from src.models.managers.common import BaseManager


class UserManager(BaseManager[User]):
    """Data access for User entities."""

    entity = User
    text_search_fields = {"shown_name": "ilike", "last_name": "ilike", "email": "ilike"}

    def __init__(self, db: AsyncSession):
        super().__init__(db)
