from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.config.postgres.db_config import get_session
from src.models import managers
from src.services.common import BaseService


class HousingService(BaseService):
    def __init__(self, db: AsyncSession):
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)


async def get_housing_service(db: AsyncSession = Depends(get_session)) -> HousingService:
    return HousingService(db=db)
