"""Sign-in for the admin UI.

SQLAdmin cannot carry a Bearer token, so it has its own credentials. The cases that matter are
the two that would silently open the panel to everyone: a blank password, and an admin left
unauthenticated while the rest of the API is closed.
"""

from unittest.mock import AsyncMock

import pytest

from src.config.admin.auth import AdminAuth, build_admin_auth
from src.config.settings import app_config


@pytest.fixture(autouse=True)
def admin_config():
    original = (app_config.admin_username, app_config.admin_password, app_config.auth_enabled)
    app_config.admin_username = "operator"
    app_config.admin_password = "s3cret"
    app_config.auth_enabled = False
    yield
    app_config.admin_username, app_config.admin_password, app_config.auth_enabled = original


def request_with(username: str, password: str):
    request = AsyncMock()
    request.form = AsyncMock(return_value={"username": username, "password": password})
    request.session = {}
    return request


class TestLogin:
    async def test_correct_credentials_open_a_session(self):
        request = request_with("operator", "s3cret")
        assert await AdminAuth(secret_key="k").login(request) is True
        assert request.session["admin"] == "operator"

    @pytest.mark.parametrize(
        "username,password",
        [("operator", "wrong"), ("someone", "s3cret"), ("operator", ""), ("", "")],
        ids=["wrong-password", "wrong-username", "empty-password", "nothing"],
    )
    async def test_anything_else_is_refused(self, username, password):
        request = request_with(username, password)
        assert await AdminAuth(secret_key="k").login(request) is False
        assert request.session == {}

    async def test_an_unset_password_refuses_everyone(self):
        # Otherwise an empty ADMIN_PASSWORD would match an empty form field.
        app_config.admin_password = None
        assert await AdminAuth(secret_key="k").login(request_with("operator", "")) is False


class TestBuild:
    def test_no_password_with_auth_on_refuses_to_start(self):
        app_config.admin_password = None
        app_config.auth_enabled = True
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            build_admin_auth()

    def test_no_password_with_auth_off_leaves_the_admin_open(self):
        # Local development: the whole API is open anyway, so the admin may stay open too.
        app_config.admin_password = None
        assert build_admin_auth() is None

    def test_a_password_builds_the_backend(self):
        assert isinstance(build_admin_auth(), AdminAuth)
