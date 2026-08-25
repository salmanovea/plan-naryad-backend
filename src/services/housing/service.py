from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.models import managers
from src.services.common import BaseService


class HousingService(BaseService):
    def __init__(self, db: AsyncSession):
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.construction_object_manager = managers.ConstructionObjectManager(db)
        self.queue_manager = managers.QueueManager(db)

    async def construction_object_ids_of_project(self, project_id: UUID) -> list[UUID]:
        """Construction objects of a project — `project_id` filters through them."""
        objects = await self.construction_object_manager.search(project_id=project_id)
        return [o.id for o in objects]

    async def with_queue(self, housings: list) -> list[dict]:
        """Attach project and queue to each housing.

        The spec wants the housing filter shown as «Очередь → Корпус», and the project filter
        alongside it. Resolving that on the client would mean three requests and a join per
        dropdown, so the chain housing → construction object → queue is walked here once.
        """
        if not housings:
            return []

        object_ids = {h.construction_object_id for h in housings if h.construction_object_id}
        objects = (
            {o.id: o for o in await self.construction_object_manager.get_by_ids(list(object_ids))} if object_ids else {}
        )
        queue_ids = {o.queue_id for o in objects.values() if o.queue_id}
        queues = {q.id: q for q in await self.queue_manager.get_by_ids(list(queue_ids))} if queue_ids else {}

        rows: list[dict] = []
        for housing in housings:
            obj = objects.get(housing.construction_object_id) if housing.construction_object_id else None
            queue = queues.get(obj.queue_id) if obj and obj.queue_id else None
            rows.append(
                {
                    **{key: getattr(housing, key) for key in ("id", "name", "complex_name", "description")},
                    "construction_object_id": housing.construction_object_id,
                    "project_id": obj.project_id if obj else None,
                    "queue_id": queue.id if queue else None,
                    "queue_name": queue.name if queue else None,
                }
            )
        return rows


async def get_housing_service(db: AsyncSession = Depends(get_session)) -> HousingService:
    return HousingService(db=db)
