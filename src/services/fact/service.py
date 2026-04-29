from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.config.postgres.db_config import get_session
from src.models import managers
from src.services.common import BaseService


class FactService(BaseService):
    def __init__(self, db: AsyncSession):
        self.work_fact_manager = managers.WorkFactManager(db)


async def get_fact_service(db: AsyncSession = Depends(get_session)) -> FactService:
    return FactService(db=db)
