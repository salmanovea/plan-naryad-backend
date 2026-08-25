"""Configuration of the Raport auth block.

Kept apart from the host service's `AppConfig` so the whole package can be copied into another
microservice as-is: it reads the environment itself and needs nothing from the service besides
being wired into the middleware stack.
"""

from typing import Optional

from pydantic_settings import BaseSettings


class AuthSettings(BaseSettings):
    """Everything the auth block reads from the environment."""

    # Master switch. Off by default so a fresh checkout and the test suite run without Keycloak.
    auth_enabled: bool = False

    # Raport group names allowed into the service, comma-separated. There is no default on
    # purpose: an empty list with auth enabled is a configuration error, not «everyone in».
    auth_allowed_groups: str = ""

    # Keycloak clients (`azp`) whose tokens are machine calls — schedulers, other services.
    # They skip the group check: a service account has no business being in a human group.
    auth_service_clients: str = ""

    # Expected `aud`. Empty means «do not check» — Keycloak has no audience mapper for us yet,
    # and turning the check on before that would reject every real token.
    auth_expected_audience: Optional[str] = None

    # Where the user's permissions come from:
    #   "authz"    — GET /api/v1/authz/users/{keycloak_id}, the target read-only endpoint;
    #   "users-me" — GET /api/v1/users/me with the user's own token, until Raport ships authz.
    auth_authz_mode: str = "users-me"
    auth_authz_path: str = "/api/v1/authz/users/{keycloak_id}"
    auth_me_path: str = "/api/v1/users/me"

    # Seconds a permissions answer is reused. Bounded by the token's own expiry, never longer.
    auth_cache_ttl: int = 120
    # Seconds a refusal is remembered, so a rejected caller in a loop does not hammer Raport.
    auth_negative_cache_ttl: int = 15
    # Seconds the Keycloak signing keys are reused. A `kid` miss refreshes them regardless.
    auth_jwks_ttl: int = 3600
    auth_timeout: float = 10.0

    # Reject users Raport marks inactive. Only meaningful once Raport actually maintains the
    # flag — see docs/raport-change-requests.md, item 11.
    auth_require_active: bool = True

    # Shared with the rest of the service; read from the same variables.
    keycloak_server_url: Optional[str] = None
    keycloak_realm: Optional[str] = None
    keycloak_verify_ssl: bool = True
    report_api_url: Optional[str] = None
    redis_url: Optional[str] = None

    @property
    def allowed_groups(self) -> set[str]:
        return {group.strip() for group in self.auth_allowed_groups.split(",") if group.strip()}

    @property
    def service_clients(self) -> set[str]:
        return {client.strip() for client in self.auth_service_clients.split(",") if client.strip()}

    @property
    def issuer(self) -> str:
        """`iss` every token must carry: {server}/realms/{realm}."""
        base = (self.keycloak_server_url or "").rstrip("/")
        return f"{base}/realms/{self.keycloak_realm}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/certs"

    @property
    def report_base_url(self) -> str:
        return (self.report_api_url or "").rstrip("/")

    class Config:
        env_file = ".env"
        extra = "ignore"


auth_settings = AuthSettings()


def validate_auth_settings(settings: AuthSettings = auth_settings) -> None:
    """Fail at startup rather than let a half-configured service run wide open.

    Everything here is a mistake that would otherwise show up as «somehow everybody has access»
    or as a 503 storm at three in the morning.
    """
    if not settings.auth_enabled:
        return

    problems = []
    if not settings.allowed_groups:
        problems.append("AUTH_ALLOWED_GROUPS is empty — with auth enabled that would let any user in")
    if not settings.keycloak_server_url or not settings.keycloak_realm:
        problems.append("KEYCLOAK_SERVER_URL and KEYCLOAK_REALM are required to verify token signatures")
    if not settings.report_base_url:
        problems.append("REPORT_API_URL is required to resolve permissions")
    if settings.auth_authz_mode not in ("authz", "users-me"):
        problems.append(f"AUTH_AUTHZ_MODE must be 'authz' or 'users-me', got {settings.auth_authz_mode!r}")

    if problems:
        raise RuntimeError("Authentication is misconfigured:\n  - " + "\n  - ".join(problems))
