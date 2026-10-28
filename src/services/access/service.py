"""Explicit business authorization helpers used by domain services."""

from collections.abc import Iterable
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres.db_config import get_session
from src.middlewares.raport_auth.settings import auth_settings
from src.models import managers
from src.models.managers.access import IdQuery
from src.services.access.schemes import GRANTS_KEY, SCOPE_KEY, AccessScope, PlanRole
from src.services.common import BaseService
from src.utils.exceptions import AccessDenied, InvalidHierarchy

SERVICE_OPERATIONS = frozenset(
    {
        ("POST", "/tasks/nightly-plan"),
        ("POST", "/tasks/transfer"),
        ("GET", "/plan-naryad/daily-assignment"),
    }
)
CONTRACTOR_READS = frozenset(
    {
        "/users/me",
        "/workforce/projects",
        "/housings/",
        "/housings/{housing_id}",
        "/housings/{housing_id}/structure",
        "/housings/{housing_id}/sections",
        "/housings/sections/{section_id}/floors",
        "/contractors/",
        "/contractors/{contractor_id}",
        "/plan-naryad/",
        "/plan-naryad/daily",
        "/plan-naryad/contractor",
        "/plan-naryad/daily-assignment",
        "/plan-naryad/{plan_item_id}",
    }
)


def session_scope(db: AsyncSession) -> AccessScope:
    """Read the explicit request context, failing closed when authentication is enabled."""
    info = db.info
    scope = info.get(SCOPE_KEY) if isinstance(info, dict) else None
    if isinstance(scope, AccessScope):
        return scope
    if auth_settings.auth_enabled:
        raise AccessDenied("Контекст прав план-наряда не установлен.")
    return AccessScope(PlanRole.LOCAL)


class AccessService(BaseService):
    """Resolve assignment filters without changing shared CRUD behavior."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.access_manager = managers.AccessManager(db)
        self.housing_manager = managers.HousingManager(db)
        self.section_manager = managers.SectionManager(db)
        self.floor_manager = managers.FloorManager(db)
        self.object_manager = managers.ConstructionObjectManager(db)

    @property
    def scope(self) -> AccessScope:
        """The permissions attached to this request's session."""
        return session_scope(self.db)

    @property
    def grants(self) -> set[str]:
        """Request-local company assignments resolved from Raport."""
        return set(self.db.info.get(GRANTS_KEY, ()))

    def initialize(self, scope: AccessScope) -> None:
        """Install a new principal without carrying grants across requests."""
        self.db.info[SCOPE_KEY] = scope
        self.db.info.pop(GRANTS_KEY, None)

    def authorize_operation(self, method: str, path: str) -> None:
        """Check section-level roles independently of query parameters and request bodies."""
        role = self.scope.role
        if role == PlanRole.SERVICE and (method, path) not in SERVICE_OPERATIONS:
            raise AccessDenied("Этот endpoint не разрешён сервисному клиенту.")
        if role == PlanRole.CONTRACTOR and (method != "GET" or path not in CONTRACTOR_READS):
            raise AccessDenied("Подрядчику доступен только дневной план-наряд.")
        if role == PlanRole.RS and (path == "/sync" or path.startswith(("/sync/", "/tasks/"))):
            raise AccessDenied("Служебные операции доступны администратору или выделенному сервису.")

    def require_business_write(self) -> None:
        """Reject mutations by a contractor before any side effects."""
        if self.scope.role == PlanRole.CONTRACTOR:
            raise AccessDenied("Подрядчику доступен только просмотр переданных заданий.")

    def require_shared_write(self) -> None:
        """Keep common dictionaries and maintenance operations administrator-only."""
        if not self.scope.unrestricted:
            raise AccessDenied("Изменение общего справочника доступно администратору.")

    def grant_assigned_contractors(self, raport_ids: Iterable[str]) -> None:
        """Remember assignments already validated against a scoped housing or cell."""
        if self.scope.role == PlanRole.RS:
            self.db.info.setdefault(GRANTS_KEY, set()).update(raport_ids)

    async def _require(self, query: IdQuery | None, ids: Iterable[UUID]) -> None:
        requested = set(ids)
        if query is None or not requested:
            return
        if await self.access_manager.matching_ids(query, requested) != requested:
            raise AccessDenied("Объект отсутствует или находится вне разрешённых назначений.")

    async def require_location(
        self, housing_id: UUID, section_id: UUID | None = None, floor_id: UUID | None = None
    ) -> None:
        """Check an explicitly selected housing/section/floor before reading Raport or writing."""
        if self.scope.unrestricted:
            return
        await self.require_housings([housing_id])
        if section_id is not None:
            await self.require_sections([section_id])
            section = await self.section_manager.get_by_id(section_id)
            if section is None or section.housing_id != housing_id:
                raise InvalidHierarchy("Секция не принадлежит выбранному корпусу.")
        if floor_id is not None:
            await self.require_floors([floor_id])
            floor = await self.floor_manager.get_by_id(floor_id)
            if floor is None or (section_id is not None and floor.section_id != section_id):
                raise InvalidHierarchy("Этаж не принадлежит выбранной секции.")
            if section_id is None:
                section = await self.section_manager.get_by_id(floor.section_id)
                if section is None or section.housing_id != housing_id:
                    raise InvalidHierarchy("Этаж не принадлежит выбранному корпусу.")

    async def require_project_object(self, project_id: UUID, object_id: UUID | None = None) -> None:
        """Check a project's optional construction-object selector."""
        if self.scope.unrestricted:
            return
        await self.require_projects([project_id])
        if object_id is not None:
            await self.require_objects([object_id])
            obj = await self.object_manager.get_by_id(object_id)
            if obj is None or obj.project_id != project_id:
                raise InvalidHierarchy("Объект строительства не принадлежит выбранному проекту.")

    def project_ids(self) -> IdQuery | None:
        """Explicit project ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.project_ids(self.scope.projects)

    async def require_projects(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected projects before the operation begins."""
        await self._require(self.project_ids(), ids)

    def object_ids(self) -> IdQuery | None:
        """Explicit object ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.object_ids(self.scope.projects)

    async def require_objects(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected objects before the operation begins."""
        await self._require(self.object_ids(), ids)

    def housing_ids(self) -> IdQuery | None:
        """Explicit housing ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.housing_ids(self.scope.projects)

    async def require_housings(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected housings before the operation begins."""
        await self._require(self.housing_ids(), ids)

    def section_ids(self) -> IdQuery | None:
        """Explicit section ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.section_ids(self.scope.projects)

    async def require_sections(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected sections before the operation begins."""
        await self._require(self.section_ids(), ids)

    def floor_ids(self) -> IdQuery | None:
        """Explicit floor ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.floor_ids(self.scope.projects)

    async def require_floors(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected floors before the operation begins."""
        await self._require(self.floor_ids(), ids)

    def plan_item_ids(self) -> IdQuery | None:
        """Explicit plan item ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.plan_item_ids(
            self.scope.projects, self.scope.contractors if self.scope.role == PlanRole.CONTRACTOR else None
        )

    async def require_plan_items(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected plan items before the operation begins."""
        await self._require(self.plan_item_ids(), ids)

    def work_fact_ids(self) -> IdQuery | None:
        """Explicit work fact ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.work_fact_ids(self.scope.projects)

    async def require_work_facts(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected work facts before the operation begins."""
        await self._require(self.work_fact_ids(), ids)

    def result_ids(self) -> IdQuery | None:
        """Explicit result ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.result_ids(self.scope.projects)

    async def require_results(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected results before the operation begins."""
        await self._require(self.result_ids(), ids)

    def summary_ids(self) -> IdQuery | None:
        """Explicit summary ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.summary_ids(self.scope.projects)

    async def require_summaries(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected summaries before the operation begins."""
        await self._require(self.summary_ids(), ids)

    def alert_ids(self) -> IdQuery | None:
        """Explicit alert ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.alert_ids(self.scope.projects)

    async def require_alerts(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected alerts before the operation begins."""
        await self._require(self.alert_ids(), ids)

    def tech_sequence_ids(self) -> IdQuery | None:
        """Explicit tech sequence ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.tech_sequence_ids(self.scope.projects)

    async def require_tech_sequences(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected tech sequences before the operation begins."""
        await self._require(self.tech_sequence_ids(), ids)

    def contractor_ids(self) -> IdQuery | None:
        """Explicit contractor ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.contractor_ids(
            self.scope.projects, self.scope.contractors if self.scope.own_contractors_only else None, self.grants
        )

    async def require_contractors(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected contractors before the operation begins."""
        await self._require(self.contractor_ids(), ids)

    async def contractor_filter(self, contractor_id: UUID | None) -> list[UUID] | None:
        """Resolve the page-level «Подрядчик» selector into the contractors the data is narrowed to.

        `None` means every contractor. An external user cannot lift the filter: without a
        choice they get their own companies, and an empty list when Raport assigns them none.
        """
        if contractor_id is not None:
            await self.require_contractors([contractor_id])
            return [contractor_id]
        if not self.scope.is_external:
            return None
        return await self.access_manager.ids(self.access_manager.contractor_ids((), self.scope.contractors))

    def budget_item_ids(self) -> IdQuery | None:
        """Explicit budget item ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.budget_item_ids(self.scope.projects)

    def headcount_fact_ids(self) -> IdQuery | None:
        """Explicit headcount fact ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.headcount_fact_ids(self.scope.projects)

    def headcount_plan_ids(self) -> IdQuery | None:
        """Explicit headcount plan ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.headcount_plan_ids(self.scope.projects)

    def challenge_ids(self) -> IdQuery | None:
        """Explicit challenge ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.challenge_ids(self.scope.projects)

    async def require_challenges(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected challenges before the operation begins."""
        await self._require(self.challenge_ids(), ids)

    def checkpoint_ids(self) -> IdQuery | None:
        """Explicit checkpoint ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.checkpoint_ids(self.scope.projects)

    def violation_ids(self) -> IdQuery | None:
        """Explicit violation ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.violation_ids(self.scope.projects)

    async def require_violations(self, ids: Iterable[UUID]) -> None:
        """Authorize all selected violations before the operation begins."""
        await self._require(self.violation_ids(), ids)

    def position_limit_ids(self) -> IdQuery | None:
        """Explicit position limit ID filter for a domain operation."""
        if self.scope.unrestricted:
            return None
        return self.access_manager.position_limit_ids(self.scope.projects, self.grants)


async def get_access_service(db: AsyncSession = Depends(get_session)) -> AccessService:
    """Construct the request's authorization service."""
    return AccessService(db=db)
