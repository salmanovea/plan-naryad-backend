"""Immutable request permissions derived from the Raport profile."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from src.utils.exceptions import AccessDenied


class AccessPrincipal(Protocol):
    """Profile fields supplied by the authentication middleware."""

    data: dict[str, Any]
    is_service: bool

    @property
    def groups(self) -> set[str]: ...


class PlanRole(str, Enum):
    """Business roles supported by the plan application."""

    ADMIN = "admin"
    CONTRACTOR = "contractor"
    RS = "rs"
    SERVICE = "service"
    LOCAL = "local"


def _raport_ids(items: Any) -> frozenset[str]:
    result: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            result.add(str(UUID(str(item.get("id")))))
        except (ValueError, TypeError, AttributeError):
            continue
    return frozenset(result)


@dataclass(frozen=True)
class AccessScope:
    """The caller's role and assignments in the Raport identifier namespace."""

    role: PlanRole
    projects: frozenset[str] = frozenset()
    contractors: frozenset[str] = frozenset()
    is_external: bool = False

    @property
    def unrestricted(self) -> bool:
        """Whether the caller is exempt from project boundaries."""
        return self.role in {PlanRole.ADMIN, PlanRole.SERVICE, PlanRole.LOCAL}

    @property
    def own_contractors_only(self) -> bool:
        """Whether the caller sees only the companies assigned to them in Raport."""
        return self.role == PlanRole.CONTRACTOR or self.is_external

    @classmethod
    def from_user(cls, user: AccessPrincipal) -> "AccessScope":
        """Resolve the documented role precedence and normalize assignments."""
        if user.is_service:
            return cls(PlanRole.SERVICE)
        if user.data.get("is_active") is False:
            raise AccessDenied("Учётная запись отключена в Рапорте.")
        if "superuser" in user.groups:
            return cls(PlanRole.ADMIN)
        if "contractor" in user.groups:
            role = PlanRole.CONTRACTOR
        elif "factgathering_user" in user.groups:
            role = PlanRole.RS
        else:
            raise AccessDenied("Нет доступа к план-наряду.")
        return cls(
            role,
            _raport_ids(user.data.get("projects")),
            _raport_ids(user.data.get("contractors")),
            is_external=user.data.get("is_external") is True,
        )


SCOPE_KEY = "plan_access"
GRANTS_KEY = "plan_assigned_contractors"
