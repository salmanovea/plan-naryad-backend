"""
Keycloak Bearer-token authentication middleware.

Enabled only when AUTH_ENABLED=true in .env. When disabled, every request
passes through without any token check — no code changes needed to toggle.

Validates the incoming Bearer token via Keycloak introspect + decode.
This project has no local User model, so the middleware returns a SimpleUser
whose username is taken from the token's preferred_username claim.
"""

from typing import Optional

from jwcrypto.common import JWException
from keycloak import KeycloakError, KeycloakOpenID
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    SimpleUser,
)
from starlette.requests import HTTPConnection

from src.config.logger import LoggerProvider
from src.config.settings import app_config

log = LoggerProvider().get_logger(__name__)

PUBLIC_ROUTES: set[str] = {
    "/health",
    "/docs",
    "/api/openapi",
    "/api/openapi.json",
    "/favicon.ico",
}

PUBLIC_ROUTE_PREFIXES: tuple[str, ...] = ()


class KeycloakMiddleware(AuthenticationBackend):
    """Validates Keycloak-issued Bearer tokens. Skips all logic when auth is disabled."""

    def __init__(self) -> None:
        self._keycloak: Optional[KeycloakOpenID] = None

    def _get_keycloak(self) -> KeycloakOpenID:
        if self._keycloak is None:
            self._keycloak = KeycloakOpenID(
                server_url=app_config.keycloak_server_url,
                client_id=app_config.keycloak_client_id,
                realm_name=app_config.keycloak_realm,
                client_secret_key=app_config.keycloak_client_secret,
                verify=app_config.keycloak_verify_ssl,
            )
        return self._keycloak

    async def authenticate(self, conn: HTTPConnection):
        if not app_config.auth_enabled:
            return None

        if self._is_public(conn):
            return None

        if conn.scope.get("method") == "OPTIONS":
            return None

        auth_header = conn.headers.get("Authorization")
        if not auth_header:
            err = AuthenticationError("Not authenticated")
            err.status_code = 401  # type: ignore[attr-defined]
            raise err

        token = self._extract_token(auth_header)

        try:
            await self._get_keycloak().a_introspect(token)
            decoded = await self._get_keycloak().a_decode_token(token=token)
        except (KeycloakError, JWException, ValueError) as e:
            log.debug(f"Token validation failed: {e}")
            raise AuthenticationError(str(e))

        sub = decoded.get("sub")
        if not sub:
            raise AuthenticationError("Token is missing 'sub' claim")

        username = decoded.get("preferred_username") or sub
        return AuthCredentials(["authenticated"]), SimpleUser(username)

    @staticmethod
    def _is_public(conn: HTTPConnection) -> bool:
        if conn.url.path in PUBLIC_ROUTES:
            return True
        return any(conn.url.path.startswith(p) for p in PUBLIC_ROUTE_PREFIXES)

    @staticmethod
    def _extract_token(auth_header: str) -> str:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        return parts[0]
