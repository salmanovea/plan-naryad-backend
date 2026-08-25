"""The Starlette authentication backend.

Order of work on every request: verify the token locally against Keycloak's keys (no network in
the common case), resolve the user's permissions through Raport (cached), then check the groups.
Machine callers — schedulers and other services — are recognised by `azp` and skip the group
check, because a service account has no business being in a human group.

Error codes are deliberate:

* **401** — «the token is missing, expired or forged»: the browser should refresh and retry.
* **403** — «the token is fine, your groups are not»: refreshing changes nothing.
* **503** — «we could not find out»: Raport or Keycloak is down, retry later.

Collapsing 401 and 403 into one code sends the frontend into an endless refresh loop, which is
precisely what Raport's own API does to its clients today.
"""

import time
from typing import Any, Optional

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    BaseUser,
)
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from src.config.logger import LoggerProvider
from src.middlewares.raport_auth.authz import AuthzClient, AuthzUnavailable, PermissionsDenied, TokenProvider
from src.middlewares.raport_auth.cache import AuthCache
from src.middlewares.raport_auth.jwks import (
    JWKSCache,
    KeycloakUnavailable,
    TokenInvalid,
    jwks_cache,
    keycloak_id_from,
    verify_token,
)
from src.middlewares.raport_auth.settings import AuthSettings, auth_settings

log = LoggerProvider().get_logger(__name__)

# Never require a token: liveness probe, OpenAPI docs, favicon. The admin UI is *not* here —
# it authenticates on its own, see src/config/admin.
DEFAULT_PUBLIC_ROUTES: tuple[str, ...] = ("/health", "/favicon.ico")

_DENIED = "__denied__"


class RaportUser(BaseUser):
    """A person, as Raport describes them."""

    is_service = False

    def __init__(self, data: dict[str, Any], claims: Optional[dict[str, Any]] = None):
        self.data = data
        self.claims = claims or {}

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return str(self.data.get("shown_name") or self.data.get("email") or self.data.get("id") or "")

    @property
    def identity(self) -> str:
        return str(self.data.get("id") or self.data.get("keycloak_id") or "")

    @property
    def groups(self) -> set[str]:
        return {str(group) for group in (self.data.get("groups") or [])}

    @property
    def is_admin(self) -> bool:
        return bool(self.data.get("is_admin"))

    @property
    def keycloak_id(self) -> str:
        """What audit fields store instead of a name — a name is personal data, an id is not."""
        return str(self.claims.get("fsk_id") or self.claims.get("sub") or self.data.get("keycloak_id") or "")


class ServiceUser(BaseUser):
    """A machine caller — Raport's scheduler or another service, identified by `azp`."""

    is_service = True

    def __init__(self, client_id: str, claims: Optional[dict[str, Any]] = None):
        self.client_id = client_id
        self.claims = claims or {}
        # `id` stays empty: a service client has no Raport user behind it, and putting the
        # client id there breaks every consumer that expects a UUID.
        self.data: dict[str, Any] = {"id": None, "shown_name": client_id, "groups": []}

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self.client_id

    @property
    def identity(self) -> str:
        return self.client_id

    @property
    def groups(self) -> set[str]:
        return set()

    @property
    def is_admin(self) -> bool:
        return False

    @property
    def keycloak_id(self) -> str:
        """The client id — a machine caller has no person behind it."""
        return self.client_id


def auth_error(message: str, status_code: int) -> AuthenticationError:
    error = AuthenticationError(message)
    error.status_code = status_code  # type: ignore[attr-defined]  # read by on_auth_error
    return error


def extract_token(auth_header: str) -> str:
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return parts[0]


class RaportAuthBackend(AuthenticationBackend):
    """Bearer authentication against Keycloak's keys plus Raport's permission model."""

    def __init__(
        self,
        settings: AuthSettings = auth_settings,
        redis_client: Any = None,
        service_token_provider: Optional[TokenProvider] = None,
        public_routes: tuple[str, ...] = DEFAULT_PUBLIC_ROUTES,
        public_route_prefixes: tuple[str, ...] = (),
        jwks: JWKSCache = jwks_cache,
    ) -> None:
        self.settings = settings
        self.cache = AuthCache(redis_client)
        self.authz = AuthzClient(settings, service_token_provider)
        self.public_routes = set(public_routes)
        self.public_route_prefixes = public_route_prefixes
        self.jwks = jwks

    async def authenticate(self, conn: HTTPConnection):
        if not self.settings.auth_enabled:
            return None
        if self._is_public(conn) or conn.scope.get("method") == "OPTIONS":
            return None

        auth_header = conn.headers.get("Authorization")
        if not auth_header:
            raise auth_error("Требуется авторизация.", 401)
        token = extract_token(auth_header)

        try:
            claims = await verify_token(token, self.settings, self.jwks)
        except TokenInvalid as e:
            log.debug(f"Token rejected: {e}")
            raise auth_error("Токен недействителен или истёк.", 401)
        except KeycloakUnavailable as e:
            raise auth_error(f"Сервис авторизации недоступен: {e}", 503)

        client_id = claims.get("azp") or claims.get("client_id")
        if client_id and client_id in self.settings.service_clients:
            return AuthCredentials(["authenticated", "service"]), ServiceUser(str(client_id), claims)

        keycloak_id = keycloak_id_from(claims)
        if not keycloak_id:
            raise auth_error("Токен не содержит идентификатор пользователя.", 401)

        permissions = await self._permissions(keycloak_id, token, claims)
        user = RaportUser(permissions, claims)
        self._check_active(user)
        self._check_groups(user)
        return AuthCredentials(["authenticated"]), user

    async def _permissions(self, keycloak_id: str, token: str, claims: dict[str, Any]) -> dict[str, Any]:
        cached = await self.cache.get(keycloak_id)
        if cached == _DENIED:
            raise auth_error("Нет доступа к план-наряду. Обратитесь к администратору Рапорта.", 403)
        if cached is not None:
            return cached

        try:
            permissions = await self.authz.fetch(keycloak_id, token)
        except PermissionsDenied as e:
            # Remembered briefly so a client in a retry loop stops hammering Raport.
            await self.cache.set(keycloak_id, _DENIED, self.settings.auth_negative_cache_ttl)
            raise auth_error(f"Нет доступа: {e}.", 403)
        except AuthzUnavailable as e:
            raise auth_error(f"Сервис авторизации недоступен: {e}", 503)

        await self.cache.set(keycloak_id, permissions, self._ttl_for(claims))
        return permissions

    def _ttl_for(self, claims: dict[str, Any]) -> int:
        """Never keep an answer longer than the token that earned it is valid."""
        ttl = self.settings.auth_cache_ttl
        expires_at = claims.get("exp")
        if isinstance(expires_at, (int, float)):
            ttl = min(ttl, int(expires_at - time.time()))
        return max(ttl, 0)

    def _check_active(self, user: RaportUser) -> None:
        # `None` means the source cannot tell — /users/me carries no such flag. Only an explicit
        # `False` blocks, otherwise switching modes would lock everyone out.
        if self.settings.auth_require_active and user.data.get("is_active") is False:
            raise auth_error("Учётная запись отключена в Рапорте.", 403)

    def _check_groups(self, user: RaportUser) -> None:
        allowed = self.settings.allowed_groups
        if not allowed:
            # Startup validation forbids this combination; belt and braces for a hand-built backend.
            raise auth_error("Список допущенных групп не настроен.", 503)
        if user.groups & allowed:
            return
        log.info(f"User {user.display_name} denied: groups={sorted(user.groups)}, allowed={sorted(allowed)}")
        raise auth_error("Нет доступа к план-наряду. Обратитесь к администратору Рапорта.", 403)

    def _is_public(self, conn: HTTPConnection) -> bool:
        path = conn.scope.get("path", "")
        if path in self.public_routes:
            return True
        return any(path.startswith(prefix) for prefix in self.public_route_prefixes)


def on_auth_error(conn: HTTPConnection, exc: Exception) -> JSONResponse:
    """Render an authentication failure in the shared error contract ({code, message})."""
    status_code = getattr(exc, "status_code", 401)
    return JSONResponse(
        status_code=status_code,
        content={"code": str(status_code), "message": str(exc) or "Требуется авторизация."},
    )
