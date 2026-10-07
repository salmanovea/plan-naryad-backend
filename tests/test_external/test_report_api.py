"""The Raport HTTP client around its cached token.

A cached token can outlive Keycloak's opinion of it — revoked, realm keys rotated. Raport then
answers 401, and the client must forget the token and try once more rather than fail a whole
nightly run on a stale credential.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.external.report.api import ReportApi, ReportApiError


def _response(status_code: int, payload: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload if payload is not None else {"data": []},
        request=httpx.Request("GET", "https://raport.test/api/v1/projects"),
    )


@pytest.fixture
def api() -> ReportApi:
    return ReportApi(base_url="https://raport.test")


async def test_a_401_is_retried_once_with_a_fresh_token(api):
    request = AsyncMock(side_effect=[_response(401, {"detail": "expired"}), _response(200, {"data": [1]})])
    with (
        patch("src.external.report.api.get_report_access_token", AsyncMock(side_effect=["stale", "fresh"])),
        patch("src.external.report.api.clear_token_cache") as clear,
        patch("httpx.AsyncClient.request", request),
    ):
        result = await api.list_projects()

    assert result == {"data": [1]}
    assert clear.call_count == 1
    assert [call.kwargs["headers"]["Authorization"] for call in request.await_args_list] == [
        "Bearer stale",
        "Bearer fresh",
    ]


async def test_a_second_401_is_an_error(api):
    request = AsyncMock(side_effect=[_response(401), _response(401)])
    with (
        patch("src.external.report.api.get_report_access_token", AsyncMock(return_value="t")),
        patch("src.external.report.api.clear_token_cache"),
        patch("httpx.AsyncClient.request", request),
    ):
        with pytest.raises(ReportApiError) as err:
            await api.list_projects()

    assert err.value.status_code == 401
    assert request.await_count == 2


async def test_other_errors_are_not_retried(api):
    request = AsyncMock(return_value=_response(500, {"detail": "boom"}))
    with (
        patch("src.external.report.api.get_report_access_token", AsyncMock(return_value="t")),
        patch("httpx.AsyncClient.request", request),
    ):
        with pytest.raises(ReportApiError):
            await api.list_projects()

    assert request.await_count == 1
