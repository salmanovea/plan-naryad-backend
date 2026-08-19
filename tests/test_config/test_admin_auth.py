"""Sign-in for the admin UI — Keycloak SSO, superuser only.

The cases that matter are the ones that would silently open the panel: a forged callback,
a user without the group, and a half-configured service that must refuse to start rather
than fall open.
"""

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import RedirectResponse

from src.config.admin.auth import AdminSSOAuth, build_admin_auth
from src.config.settings import app_config
from src.middlewares.raport_auth.settings import auth_settings

SUPERUSER = {"id": "u-1", "keylock_id": "kc-1", "groups": ["superuser", "smr_management_user"]}
MERE_MORTAL = {"id": "u-2", "keylock_id": "kc-2", "groups": ["plan_naryad"]}


@pytest.fixture(autouse=True)
def admin_config():
    original = (
        app_config.admin_keycloak_client_id,
        app_config.admin_allowed_groups,
        app_config.auth_enabled,
        auth_settings.keycloak_server_url,
        auth_settings.keycloak_realm,
    )
    app_config.admin_keycloak_client_id = "front-client"
    app_config.admin_allowed_groups = "superuser"
    app_config.auth_enabled = True
    auth_settings.keycloak_server_url = "https://keycloak.test/auth"
    auth_settings.keycloak_realm = "fsk"
    yield
    (
        app_config.admin_keycloak_client_id,
        app_config.admin_allowed_groups,
        app_config.auth_enabled,
        auth_settings.keycloak_server_url,
        auth_settings.keycloak_realm,
    ) = original


def backend() -> AdminSSOAuth:
    return AdminSSOAuth(secret_key="k", base_url="/pn/admin")


def make_request(path: str = "/pn/admin/", session: dict | None = None, query: str = "") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [(b"host", b"stand.test")],
            "query_string": query.encode(),
            "scheme": "https",
            "server": ("stand.test", 443),
        }
    )
    request.scope["session"] = session if session is not None else {}
    return request


def sso_mocks(profile=SUPERUSER):
    """Keycloak token endpoint + local verification + Raport groups, all canned."""
    token_response = httpx.Response(
        200, json={"access_token": "the-token"}, request=httpx.Request("POST", "https://keycloak.test")
    )
    return (
        patch("httpx.AsyncClient.post", AsyncMock(return_value=token_response)),
        patch("src.config.admin.auth.verify_token", AsyncMock(return_value={"sub": "kc-1"})),
        patch(
            "src.middlewares.raport_auth.authz.AuthzClient.fetch",
            AsyncMock(return_value={**profile, "keycloak_id": profile["keylock_id"]}),
        ),
    )


async def run_callback(session: dict, query: str, profile=SUPERUSER):
    token_mock, verify_mock, fetch_mock = sso_mocks(profile)
    request = make_request("/pn/admin/oauth/callback", session=session, query=query)
    with token_mock, verify_mock, fetch_mock:
        response = await backend().callback(request)
    return response, request


class TestAuthenticate:
    async def test_no_session_redirects_to_keycloak_with_pkce(self):
        request = make_request()
        response = await backend().authenticate(request)

        assert isinstance(response, RedirectResponse)
        location = response.headers["location"]
        assert location.startswith("https://keycloak.test/auth/realms/fsk/protocol/openid-connect/auth?")
        assert "code_challenge_method=S256" in location
        assert "client_id=front-client" in location
        # state must land in the session, or the callback cannot tell ours from a forged one
        assert request.session["oauth"]["state"] in location

    async def test_a_live_session_is_enough(self):
        session = {"admin": {"keycloak_id": "kc-1", "expires_at": time.time() + 60}}
        assert await backend().authenticate(make_request(session=session)) is True

    async def test_an_expired_session_goes_back_to_keycloak(self):
        session = {"admin": {"keycloak_id": "kc-1", "expires_at": time.time() - 1}}
        response = await backend().authenticate(make_request(session=session))
        assert isinstance(response, RedirectResponse)
        assert "admin" not in session

    async def test_the_password_form_is_not_a_way_in(self):
        assert await backend().login(make_request()) is False


class TestCallback:
    async def test_superuser_gets_a_session(self):
        session = {"oauth": {"state": "s1", "verifier": "v1"}}
        response, request = await run_callback(session, "code=c1&state=s1")

        assert isinstance(response, RedirectResponse)
        assert response.headers["location"] == "/pn/admin/"
        assert request.session["admin"]["keycloak_id"] == "kc-1"
        assert request.session["admin"]["expires_at"] > time.time()

    async def test_a_user_without_the_group_is_refused(self):
        session = {"oauth": {"state": "s1", "verifier": "v1"}}
        response, request = await run_callback(session, "code=c1&state=s1", profile=MERE_MORTAL)

        assert response.status_code == 403
        assert "admin" not in request.session

    async def test_a_forged_state_restarts_the_flow_instead_of_logging_in(self):
        session = {"oauth": {"state": "s1", "verifier": "v1"}}
        response, request = await run_callback(session, "code=c1&state=WRONG")

        assert isinstance(response, RedirectResponse)
        assert "openid-connect/auth?" in response.headers["location"]
        assert "admin" not in request.session

    async def test_keycloak_error_is_a_403_not_a_session(self):
        response, request = await run_callback({}, "error=access_denied")
        assert response.status_code == 403

    async def test_logout_clears_the_session(self):
        request = make_request(session={"admin": {"keycloak_id": "kc-1", "expires_at": time.time() + 60}})
        assert await backend().logout(request) is True
        assert request.session == {}


class TestBuild:
    def test_auth_on_without_a_client_refuses_to_start(self):
        app_config.admin_keycloak_client_id = None
        with pytest.raises(RuntimeError, match="ADMIN_KEYCLOAK_CLIENT_ID"):
            build_admin_auth("/pn/admin")

    def test_auth_off_leaves_the_admin_open(self):
        app_config.auth_enabled = False
        assert build_admin_auth("/pn/admin") is None

    def test_a_configured_client_builds_the_backend(self):
        assert isinstance(build_admin_auth("/pn/admin"), AdminSSOAuth)
