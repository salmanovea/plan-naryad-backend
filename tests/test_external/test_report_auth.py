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
from src.external.report.auth import (
    ReportAuthError,
    clear_token_cache,
    get_report_access_token,
    get_report_service_token,
)


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
    clear_token_cache()
    yield
    clear_token_cache()
    for key, value in original.items():
        setattr(app_config, key, value)


# A token that is already past its lifetime but still carries a usable refresh token.
_EXPIRED_WITH_REFRESH = {"access_token": "t1", "expires_in": 0, "refresh_token": "r", "refresh_expires_in": 1800}


def _response(status_code: int = 200, payload=None) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload if payload is not None else {"access_token": "t", "expires_in": 300},
        request=httpx.Request("POST", "https://keycloak.test"),
    )


def mock_token(status_code: int = 200, payload=None):
    return patch("httpx.AsyncClient.post", AsyncMock(return_value=_response(status_code, payload)))


def mock_token_sequence(*responses: httpx.Response):
    return patch("httpx.AsyncClient.post", AsyncMock(side_effect=list(responses)))


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


async def test_the_token_is_cached_for_its_lifetime():
    """~16 000 Raport calls a night must not mean 16 000 token requests."""
    with mock_token() as post:
        first = await get_report_access_token()
        second = await get_report_access_token()

    assert first == second == "t"
    assert post.await_count == 1


async def test_grants_are_cached_separately():
    with mock_token() as post:
        await get_report_access_token()
        await get_report_service_token()

    assert post.await_count == 2


async def test_an_expired_token_is_renewed_through_the_refresh_token():
    issued = _response(payload=_EXPIRED_WITH_REFRESH)
    renewed = _response(payload={"access_token": "t2", "expires_in": 300})
    with mock_token_sequence(issued, renewed) as post:
        assert await get_report_access_token() == "t1"
        assert await get_report_access_token() == "t2"

    data = post.await_args_list[1].kwargs["data"]
    assert data["grant_type"] == "refresh_token"
    assert data["refresh_token"] == "r"
    assert "password" not in data


async def test_a_failed_refresh_falls_back_to_the_full_grant():
    issued = _response(payload=_EXPIRED_WITH_REFRESH)
    refused = _response(400, {"error": "invalid_grant"})
    reissued = _response(payload={"access_token": "t3", "expires_in": 300})
    with mock_token_sequence(issued, refused, reissued) as post:
        await get_report_access_token()
        assert await get_report_access_token() == "t3"

    assert [call.kwargs["data"]["grant_type"] for call in post.await_args_list] == [
        "password",
        "refresh_token",
        "password",
    ]


async def test_a_token_without_lifetime_is_not_cached():
    with mock_token(payload={"access_token": "t"}) as post:
        await get_report_access_token()
        await get_report_access_token()

    assert post.await_count == 2


async def test_clearing_the_cache_forces_a_new_token():
    with mock_token() as post:
        await get_report_access_token()
        clear_token_cache()
        await get_report_access_token()

    assert post.await_count == 2
