from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.config.postgres.db_config import get_session
from src.models import managers
from src.services.common import BaseService


class WorkService(BaseService):
    def __init__(self, db: AsyncSession):
        self.work_group_manager = managers.WorkGroupManager(db)
        self.work_type_manager = managers.WorkTypeManager(db)
        self.tech_sequence_manager = managers.TechSequenceItemManager(db)
        self.housing_manager = managers.HousingManager(db)


async def get_work_service(db: AsyncSession = Depends(get_session)) -> WorkService:
    return WorkService(db=db)
