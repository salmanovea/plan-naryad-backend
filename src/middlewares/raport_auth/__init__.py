"""Authentication and authorization against the Raport ecosystem.

Self-contained block, meant to be copied into any microservice of the ecosystem: it reads its own
environment variables, verifies Keycloak tokens locally and asks Raport for the user's groups.
The host service only wires it into the middleware stack:

    from src.config.redis import redis
    from src.external.report.auth import get_report_access_token
    from src.middlewares.raport_auth import RaportAuthBackend, on_auth_error, validate_auth_settings

    validate_auth_settings()
    app.add_middleware(
        AuthenticationMiddleware,
        backend=RaportAuthBackend(redis_client=redis, service_token_provider=get_report_access_token),
        on_error=on_auth_error,
    )
"""

from src.middlewares.raport_auth.authz import AuthzClient, AuthzUnavailable, PermissionsDenied
from src.middlewares.raport_auth.backend import (
    DEFAULT_PUBLIC_ROUTES,
    RaportAuthBackend,
    RaportUser,
    ServiceUser,
    on_auth_error,
)
from src.middlewares.raport_auth.jwks import KeycloakUnavailable, TokenInvalid, jwks_cache, verify_token
from src.middlewares.raport_auth.settings import AuthSettings, auth_settings, validate_auth_settings
