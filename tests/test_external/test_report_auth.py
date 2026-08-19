"""Token grants for talking to Raport.

Which grant is used is not cosmetic: Raport accepts only a client-credentials token on its
`/authz` endpoint, and a public client cannot issue one at all — verified against the local
Keycloak, which answers a public client with «Public client not allowed to retrieve service
account».
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.config.settings import app_config
from src.external.report.auth import ReportAuthError, get_report_access_token, get_report_service_token


@pytest.fixture(autouse=True)
def keycloak_config():
    original = {
        key: getattr(app_config, key)
        for key in (
            "keycloak_server_url",
            "keycloak_realm",
            "report_keycloak_client_id",
            "report_keycloak_client_secret",
            "report_service_client_id",
            "report_service_client_secret",
        )
    }
    app_config.keycloak_server_url = "https://keycloak.test/auth"
    app_config.keycloak_realm = "fsk"
    app_config.report_keycloak_client_id = "front-client"
    app_config.report_keycloak_client_secret = "front-secret"
    app_config.report_service_client_id = None
    app_config.report_service_client_secret = None
    yield
    for key, value in original.items():
        setattr(app_config, key, value)


def mock_token(status_code: int = 200, payload=None):
    response = httpx.Response(
        status_code,
        json=payload if payload is not None else {"access_token": "t"},
        request=httpx.Request("POST", "https://keycloak.test"),
    )
    return patch("httpx.AsyncClient.post", AsyncMock(return_value=response))


async def test_data_calls_use_the_password_grant():
    with mock_token() as post:
        assert await get_report_access_token() == "t"
    assert post.await_args.kwargs["data"]["grant_type"] == "password"


async def test_authz_calls_use_client_credentials():
    with mock_token() as post:
        assert await get_report_service_token() == "t"
    data = post.await_args.kwargs["data"]
    assert data["grant_type"] == "client_credentials"
    assert "username" not in data


async def test_the_service_client_can_be_a_different_one():
    app_config.report_service_client_id = "api"
    app_config.report_service_client_secret = "api-secret"
    with mock_token() as post:
        await get_report_service_token()
    data = post.await_args.kwargs["data"]
    assert (data["client_id"], data["client_secret"]) == ("api", "api-secret")


async def test_it_falls_back_to_the_data_client_when_unset():
    with mock_token() as post:
        await get_report_service_token()
    assert post.await_args.kwargs["data"]["client_id"] == "front-client"


async def test_keycloak_refusal_surfaces_as_a_typed_error():
    # This is what a public client gets back for client_credentials.
    with mock_token(401, {"error": "unauthorized_client"}):
        with pytest.raises(ReportAuthError):
            await get_report_service_token()


async def test_missing_keycloak_config_is_a_typed_error():
    app_config.keycloak_server_url = None
    with pytest.raises(ReportAuthError):
        await get_report_service_token()
