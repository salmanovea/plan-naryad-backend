from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.config.postgres.db_config import get_session
from src.models import managers
from src.services.common import BaseService


class ContractorService(BaseService):
    def __init__(self, db: AsyncSession):
        self.contractor_manager = managers.ContractorManager(db)
        self.assignment_manager = managers.ContractorAssignmentManager(db)


async def get_contractor_service(db: AsyncSession = Depends(get_session)) -> ContractorService:
    return ContractorService(db=db)
