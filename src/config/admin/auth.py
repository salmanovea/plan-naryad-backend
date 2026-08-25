"""Sign-in for the admin UI — Keycloak SSO, `superuser` group from Raport.

SQLAdmin cannot carry the Bearer token the rest of the API expects, so the admin runs the
classic authorization-code + PKCE flow entirely on the server: no session — redirect to
Keycloak, exchange the code on the callback, verify the token with the same JWKS module the
API uses, ask Raport for the groups through the same AuthzClient, and only `superuser` gets a
session. The session is short-lived on purpose: re-entry goes through Keycloak silently while
the SSO session is alive, and every re-entry re-reads the groups — revoking `superuser`
locks the admin out within ADMIN_SESSION_TTL.

Consequence accepted by design: when Keycloak or Raport is down, the admin is not reachable
either (an already-issued session keeps working until its TTL).
"""

import secrets
import time
from base64 import urlsafe_b64encode
from hashlib import sha256
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response

from src.config.logger import LoggerProvider
from src.config.settings import app_config
from src.external.report.auth import get_report_service_token
from src.middlewares.raport_auth.authz import AuthzClient, AuthzUnavailable, PermissionsDenied
from src.middlewares.raport_auth.jwks import KeycloakUnavailable, TokenInvalid, keycloak_id_from, verify_token
from src.middlewares.raport_auth.settings import auth_settings

log = LoggerProvider().get_logger(__name__)

CALLBACK_PATH = "/oauth/callback"


def _forbidden(message: str) -> Response:
    return PlainTextResponse(message, status_code=403)


class AdminSSOAuth(AuthenticationBackend):
    """Keycloak authorization-code flow for SQLAdmin; access = the groups in ADMIN_ALLOWED_GROUPS."""

    def __init__(self, secret_key: str, base_url: str) -> None:
        super().__init__(secret_key=secret_key)
        self.base_url = base_url.rstrip("/")

    async def login(self, request: Request) -> bool:
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Any:
        session = request.session.get("admin") or {}
        if session.get("expires_at", 0) > time.time():
            return True
        request.session.pop("admin", None)
        return self.authorize_redirect(request)

    def authorize_redirect(self, request: Request) -> RedirectResponse:
        """Send the browser to Keycloak, carrying state and a PKCE challenge in the session."""
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        request.session["oauth"] = {"state": state, "verifier": verifier}

        query = urlencode(
            {
                "client_id": app_config.admin_keycloak_client_id,
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": self._callback_url(request),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return RedirectResponse(f"{auth_settings.issuer}/protocol/openid-connect/auth?{query}", status_code=302)

    async def callback(self, request: Request) -> Response:
        """Back from Keycloak: check state, trade the code, verify, ask Raport for the groups."""
        oauth = request.session.pop("oauth", None) or {}
        state, code = request.query_params.get("state"), request.query_params.get("code")
        if error := request.query_params.get("error"):
            return _forbidden(f"Keycloak отказал во входе: {error}")
        if not code or not state or state != oauth.get("state"):
            return self.authorize_redirect(request)

        try:
            token = await self._exchange_code(code, oauth["verifier"], self._callback_url(request))
            claims = await verify_token(token)
        except TokenInvalid as e:
            log.warning(f"Admin sign-in: Keycloak returned an unusable token: {e}")
            return _forbidden("Токен не прошёл проверку.")
        except (KeycloakUnavailable, AuthzUnavailable) as e:
            return PlainTextResponse(f"Сервис авторизации недоступен: {e}", status_code=503)

        keycloak_id = keycloak_id_from(claims)
        if not keycloak_id:
            return _forbidden("Токен не содержит идентификатор пользователя.")

        try:
            profile = await AuthzClient(auth_settings, get_report_service_token).fetch(keycloak_id, token)
        except PermissionsDenied as e:
            return _forbidden(f"Нет доступа: {e}.")
        except AuthzUnavailable as e:
            return PlainTextResponse(f"Сервис авторизации недоступен: {e}", status_code=503)

        groups = set(profile.get("groups") or [])
        allowed = app_config.admin_groups
        if not groups & allowed:
            log.info(f"Admin sign-in refused for {keycloak_id}: groups={sorted(groups)}, allowed={sorted(allowed)}")
            return _forbidden("Админка доступна только группе superuser.")

        request.session["admin"] = {
            "keycloak_id": keycloak_id,
            "expires_at": time.time() + app_config.admin_session_ttl,
        }
        log.info(f"Admin sign-in: {keycloak_id}")
        return RedirectResponse(self.base_url + "/", status_code=302)

    async def _exchange_code(self, code: str, verifier: str, redirect_uri: str) -> str:
        payload = {
            "grant_type": "authorization_code",
            "client_id": app_config.admin_keycloak_client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }

        try:
            async with httpx.AsyncClient(
                timeout=auth_settings.auth_timeout, verify=auth_settings.keycloak_verify_ssl
            ) as http:
                response = await http.post(f"{auth_settings.issuer}/protocol/openid-connect/token", data=payload)
        except httpx.HTTPError as e:
            raise KeycloakUnavailable(f"cannot reach Keycloak: {e}")

        if response.status_code != 200:
            raise TokenInvalid(f"Keycloak returned {response.status_code}: {response.text[:200]}")
        token = response.json().get("access_token")
        if not token:
            raise TokenInvalid("Keycloak response carries no access_token")
        return str(token)

    def _callback_url(self, request: Request) -> str:
        """Absolute callback URL, trusting the proxy headers — behind nginx the scheme is theirs."""
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
        return f"{scheme}://{host}{self.base_url}{CALLBACK_PATH}"


def build_admin_auth(base_url: str) -> Optional[AdminSSOAuth]:
    """The sign-in backend, or None to leave the admin open.

    Open is allowed only while the rest of the service is open too (AUTH_ENABLED=false — local
    development). With auth on, a misconfigured admin must fail the start, not fall open.
    """
    if not app_config.auth_enabled:
        log.warning("AUTH_ENABLED=false — the admin UI is open (fine only for local development)")
        return None

    if not app_config.admin_keycloak_client_id:
        raise RuntimeError(
            "ADMIN_KEYCLOAK_CLIENT_ID is not set: with AUTH_ENABLED=true the admin UI must go "
            "through Keycloak, there is no password fallback"
        )
    if not app_config.admin_session_secret:
        log.warning("ADMIN_SESSION_SECRET is not set — admin sessions will not survive a restart")

    return AdminSSOAuth(
        secret_key=app_config.admin_session_secret or secrets.token_urlsafe(32),
        base_url=base_url,
    )
