from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.middlewares.raport_auth.backend import RaportUser, ServiceUser
from src.middlewares.raport_auth.settings import auth_settings
from src.services.access.schemes import AccessScope, PlanRole
from src.services.access.service import session_scope
from src.utils.exceptions import AccessDenied


@pytest.mark.parametrize(
    ("groups", "role"),
    [
        (["superuser"], PlanRole.ADMIN),
        (["superuser", "contractor"], PlanRole.ADMIN),
        (["contractor"], PlanRole.CONTRACTOR),
        (["contractor", "factgathering_user"], PlanRole.CONTRACTOR),
        (["contractor", "factgathering_user", "factgathering_editor"], PlanRole.CONTRACTOR),
        (["factgathering_user"], PlanRole.RS),
        (["factgathering_user", "factgathering_editor"], PlanRole.RS),
    ],
)
def test_existing_group_precedence(groups, role):
    assert AccessScope.from_user(RaportUser({"groups": groups})).role == role


@pytest.mark.parametrize("groups", [[], ["supervisor"], ["plan_naryad"], ["factgathering_editor"], ["unknown"]])
def test_other_groups_do_not_grant_plan_access(groups):
    with pytest.raises(AccessDenied):
        AccessScope.from_user(RaportUser({"groups": groups, "is_admin": True}))


def test_inactive_admin_is_denied():
    with pytest.raises(AccessDenied):
        AccessScope.from_user(RaportUser({"groups": ["superuser"], "is_active": False}))


def test_assignments_are_normalised_and_malformed_entries_fail_closed():
    project, contractor = uuid4(), uuid4()
    scope = AccessScope.from_user(
        RaportUser(
            {
                "groups": ["contractor"],
                "projects": [{"id": str(project).upper()}, {"id": "bad"}, "bad", {}],
                "contractors": [{"id": contractor}],
            }
        )
    )
    assert scope.projects == {str(project)}
    assert scope.contractors == {str(contractor)}
    assert AccessScope.from_user(RaportUser({"groups": ["factgathering_user"], "projects": "bad"})).projects == set()


def test_service_role_is_distinct_from_admin():
    assert AccessScope.from_user(ServiceUser("api")).role == PlanRole.SERVICE


def test_missing_scope_is_denied_when_auth_is_enabled(monkeypatch):
    monkeypatch.setattr(auth_settings, "auth_enabled", True)
    with pytest.raises(AccessDenied):
        session_scope(AsyncSession())
