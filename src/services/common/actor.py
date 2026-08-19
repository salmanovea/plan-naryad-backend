"""Who is behind the request.

The action log and `rs_confirmed_by` record the caller's Keycloak id, **not** their name:
a name is personal data and audit rows live forever, an opaque id is resolvable through
Raport when someone actually needs to know. The middleware puts the user into the request
scope, nothing here talks to Raport itself.
"""

from typing import Optional

from starlette.requests import Request

# What gets written when nobody is authenticated: AUTH_ENABLED=false locally, or a job
# triggered by Raport's scheduler rather than by a person.
SYSTEM_ACTOR = "system"


def current_user(request: Request) -> Optional[object]:
    """The authenticated Raport user, or None when auth is disabled."""
    user = request.scope.get("user")
    return user if user is not None and getattr(user, "is_authenticated", False) else None


def current_actor(request: Request) -> str:
    """What to write into audit fields — the caller's Keycloak id, or «system» when auth is off.

    Deliberately not the display name: ФИО in an append-only log is a personal-data liability
    (152-ФЗ), while the id points to the same person via Raport without storing anything personal.
    """
    user = current_user(request)
    return getattr(user, "keycloak_id", "") or SYSTEM_ACTOR
