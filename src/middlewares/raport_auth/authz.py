"""Who the user is and what they may do — answered by Raport.

Two sources, picked by AUTH_AUTHZ_MODE:

* ``authz``    — ``GET /api/v1/authz/users/{keycloak_id}`` with the *service* token. Read-only,
                 keyed by user rather than by token, so one answer serves every request of that
                 user for the whole TTL. This is the target; see docs/raport-change-requests.md.
* ``users-me`` — ``GET /api/v1/users/me`` with the *user's* token. What Raport offers today.
                 It is not read-only (it rewrites `last_login` and re-applies default groups on
                 every call), which is exactly why the cache in front of it is not optional.

Both answers are normalised into one shape, so switching modes changes a variable, not code.
"""

from typing import Any, Awaitable, Callable, Optional

import httpx

from src.config.logger import LoggerProvider
from src.middlewares.raport_auth.settings import AuthSettings, auth_settings

log = LoggerProvider().get_logger(__name__)

TokenProvider = Callable[[], Awaitable[str]]


class PermissionsDenied(Exception):
    """Raport knows the token or the user, and says no."""


class AuthzUnavailable(Exception):
    """Raport could not answer at all — a different thing from «denied»."""


def normalise(payload: dict[str, Any]) -> dict[str, Any]:
    """Bring both endpoints to one shape.

    `is_active` and `is_admin` stay `None` when the source cannot tell (that is `/users/me`
    today): a missing flag must not read as `False` and lock everyone out.
    """
    return {
        "id": payload.get("id"),
        "keycloak_id": payload.get("keylock_id"),
        "shown_name": payload.get("shown_name"),
        "first_name": payload.get("first_name"),
        "last_name": payload.get("last_name"),
        "middle_name": payload.get("middle_name"),
        "email": payload.get("email"),
        "is_external": payload.get("is_external"),
        "is_active": payload.get("is_active"),
        "is_admin": payload.get("is_admin"),
        "groups": list(payload.get("groups") or []),
        "projects": payload.get("projects") or [],
        "contractors": payload.get("contractors") or [],
    }


class AuthzClient:
    """Fetches a user's permissions from Raport."""

    def __init__(
        self,
        settings: AuthSettings = auth_settings,
        service_token_provider: Optional[TokenProvider] = None,
    ) -> None:
        self._settings = settings
        self._service_token_provider = service_token_provider

    async def fetch(self, keycloak_id: str, user_token: str) -> dict[str, Any]:
        if self._settings.auth_authz_mode == "authz":
            return await self._fetch_authz(keycloak_id)
        return await self._fetch_users_me(user_token)

    async def _fetch_authz(self, keycloak_id: str) -> dict[str, Any]:
        if self._service_token_provider is None:
            raise AuthzUnavailable("AUTH_AUTHZ_MODE=authz requires a service token provider")
        try:
            token = await self._service_token_provider()
        except Exception as e:  # noqa: BLE001 — any failure to authenticate ourselves is an outage
            raise AuthzUnavailable(f"cannot obtain the service token: {e}")

        path = self._settings.auth_authz_path.format(keycloak_id=keycloak_id)
        status_code, payload, detail = await self._get(path, token)

        # 404 — the person has never logged into Raport, so it has no record and no groups.
        if status_code == 404:
            raise PermissionsDenied("пользователь не заведён в Рапорте")
        # 401/403 mean *our* service token was refused, not that this user lacks access. Treating
        # it as a refusal would show every user «you are not registered» and cache that, hiding a
        # plain misconfiguration (the client missing from Raport's SERVICE_CLIENT_IDS).
        if status_code in (401, 403) or payload is None:
            raise AuthzUnavailable(
                f"Raport refused the service token on {path} (HTTP {status_code}: {detail}); check that our "
                f"client is listed in its SERVICE_CLIENT_IDS and that it accepts client-credentials tokens"
            )
        return normalise(payload)

    async def _fetch_users_me(self, user_token: str) -> dict[str, Any]:
        # Here the token is the user's own, so a refusal really is about them.
        _, payload, _detail = await self._get(self._settings.auth_me_path, user_token)
        if payload is None:
            raise PermissionsDenied("Рапорт отклонил токен")
        return normalise(payload)

    async def _get(self, path: str, token: str) -> tuple[int, Optional[dict[str, Any]], str]:
        """Returns (status, payload, detail); payload is None when Raport refuses (401/403/404).

        `detail` carries Raport's own words for a refusal — without them «HTTP 401» says nothing
        about whether the client is not whitelisted or the token was not accepted at all.
        """
        base = self._settings.report_base_url
        if not base:
            raise AuthzUnavailable("REPORT_API_URL is not configured")

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.auth_timeout,
                verify=self._settings.keycloak_verify_ssl,
                follow_redirects=True,
            ) as http:
                response = await http.get(base + path, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as e:
            raise AuthzUnavailable(f"cannot reach Raport at {base + path}: {e}")

        # Raport answers 403 for an expired or unknown token — its `on_auth_error` defaults to
        # 403 and the expiry error carries no status (megashablon/fastapi_server.py:113). Here it
        # simply means «no answer for you», the caller decides what that maps to.
        if response.status_code in (401, 403, 404):
            return response.status_code, None, response.text[:200].replace("\n", " ")
        if response.status_code != 200:
            raise AuthzUnavailable(f"Raport returned {response.status_code} for {path}")

        try:
            payload = response.json()
        except ValueError:
            raise AuthzUnavailable(f"Raport returned a non-JSON body for {path}")

        # Raport wraps most endpoints into {code, message, data} but not /users/me; accept both,
        # so a future change of the authz contract does not break us.
        if isinstance(payload, dict) and "data" in payload and "code" in payload:
            payload = payload.get("data")
        return response.status_code, (payload if isinstance(payload, dict) and payload else None), ""
