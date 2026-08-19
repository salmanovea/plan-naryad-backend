"""Sign-in for the admin UI.

SQLAdmin is a browser UI: it cannot carry the Bearer token the rest of the API expects, so it
gets its own credentials from the environment instead of being left open, as it was before.

Deliberately not tied to Keycloak: the admin panel is an operator tool that has to work when
Keycloak or Raport is down — that is often exactly when someone needs it.
"""

import secrets
from typing import Optional

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse

from src.config.logger import LoggerProvider
from src.config.settings import app_config

log = LoggerProvider().get_logger(__name__)


class AdminAuth(AuthenticationBackend):
    """Username and password from ADMIN_USERNAME / ADMIN_PASSWORD, session kept in a cookie."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")

        expected_password = app_config.admin_password or ""
        username_ok = secrets.compare_digest(username, app_config.admin_username)
        password_ok = bool(expected_password) and secrets.compare_digest(password, expected_password)
        if not (username_ok and password_ok):
            log.warning(f"Admin sign-in refused for {username!r}")
            return False

        request.session.update({"admin": username})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request):
        if request.session.get("admin"):
            return True
        return RedirectResponse(request.url_for("admin:login"), status_code=302)


def build_admin_auth() -> Optional[AdminAuth]:
    """The sign-in backend, or None to leave the admin open.

    Open is allowed only while the rest of the service is open too (AUTH_ENABLED=false — local
    development). Once authentication is on, an admin without a password would be the one
    unauthenticated way into the data, so the service refuses to start instead.
    """
    if not app_config.admin_password:
        if app_config.auth_enabled:
            raise RuntimeError(
                "ADMIN_PASSWORD is not set: with AUTH_ENABLED=true the admin UI would be the one "
                "unauthenticated way into the data"
            )
        log.warning("ADMIN_PASSWORD is not set — the admin UI is open (fine only for local development)")
        return None

    if not app_config.admin_session_secret:
        log.warning("ADMIN_SESSION_SECRET is not set — admin sessions will not survive a restart")
    return AdminAuth(secret_key=app_config.admin_session_secret or secrets.token_urlsafe(32))
