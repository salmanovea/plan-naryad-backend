"""
Keycloak token fetchers for talking to Raport.

Two grants, because Raport treats them differently:

* **password** (`get_report_access_token`) — acts as a technical *user*, which is what the data
  endpoints need: they resolve projects and contractors through that user's own permissions.
* **client_credentials** (`get_report_service_token`) — acts as a *service client*. Raport accepts
  it only for service-to-service endpoints (`GET /authz/users/{id}`), and recognises it by `azp`
  being listed in its `SERVICE_CLIENT_IDS`. A password-grant token is rejected there: Raport's
  `resolve_service_client` requires the token to be marked as client-credentials
  (`megashablon/src/middlewares/keycloak_middleware.py:63`).

Tokens are cached per grant for their lifetime. An expired one is renewed through the refresh
token when Keycloak issued one, else requested anew. A nightly run makes ~16 000 Raport calls;
asking Keycloak for a token before each of them is exactly what its throttling is built to stop.

Copied into src/external/report/auth.py by the report-microservice skill.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from src.config.logger import LoggerProvider
from src.config.settings import app_config

log = LoggerProvider().get_logger(__name__)

_TOKEN_PATH = "/realms/{realm}/protocol/openid-connect/token"
_EXPIRY_LEEWAY = 30.0


class ReportAuthError(RuntimeError):
    """Raised when the Raport service account fails to obtain an access token."""


@dataclass
class _CachedToken:
    """One grant's token with its Keycloak lifetimes, on the monotonic clock."""

    access_token: str
    expires_at: float
    refresh_token: Optional[str]
    refresh_expires_at: float

    def is_live(self, now: float) -> bool:
        return now < self.expires_at - _EXPIRY_LEEWAY

    def can_refresh(self, now: float) -> bool:
        return bool(self.refresh_token) and now < self.refresh_expires_at - _EXPIRY_LEEWAY


_cache: dict[str, _CachedToken] = {}
_locks: dict[str, asyncio.Lock] = {}


def clear_token_cache() -> None:
    """Forget every cached token — after a 401 from Raport, and between tests."""
    _cache.clear()


async def _post_token(payload: dict[str, Optional[str]]) -> dict[str, Any]:
    server_url = (app_config.keycloak_server_url or "").rstrip("/")
    realm = app_config.keycloak_realm

    if not server_url or not realm:
        raise ReportAuthError("KEYCLOAK_SERVER_URL and KEYCLOAK_REALM must be set")

    token_url = server_url + _TOKEN_PATH.format(realm=realm)
    data = {key: value for key, value in payload.items() if value is not None}

    async with httpx.AsyncClient(
        timeout=10.0,
        verify=app_config.keycloak_verify_ssl,
    ) as http:
        response = await http.post(token_url, data=data)

    if response.status_code != 200:
        log.error(f"Report Keycloak token request failed: status={response.status_code} body={response.text[:500]}")
        raise ReportAuthError(f"Keycloak returned {response.status_code} while issuing the Raport token")

    body = response.json()
    if not body.get("access_token"):
        raise ReportAuthError("Keycloak response did not contain access_token")
    return body


def _remember(key: str, body: dict[str, Any]) -> _CachedToken:
    now = time.monotonic()
    token = _CachedToken(
        access_token=body["access_token"],
        expires_at=now + float(body.get("expires_in") or 0),
        refresh_token=body.get("refresh_token"),
        refresh_expires_at=now + float(body.get("refresh_expires_in") or 0),
    )
    _cache[key] = token
    return token


async def _cached_token(key: str, payload: dict[str, Optional[str]]) -> str:
    """A live token for the grant, going to Keycloak only when the cached one is gone.

    Concurrent callers share one lock per grant so a burst of requests at expiry produces
    a single token request, not one per caller.
    """
    cached = _cache.get(key)
    if cached and cached.is_live(time.monotonic()):
        return cached.access_token

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _cache.get(key)
        if cached and cached.is_live(now):
            return cached.access_token

        if cached and cached.can_refresh(now):
            try:
                body = await _post_token(
                    {
                        "grant_type": "refresh_token",
                        "client_id": payload["client_id"],
                        "client_secret": payload["client_secret"],
                        "refresh_token": cached.refresh_token,
                    }
                )
                return _remember(key, body).access_token
            except ReportAuthError as err:
                log.warning("Raport token refresh failed, requesting a new one: %s", err)

        body = await _post_token(payload)
        return _remember(key, body).access_token


async def get_report_access_token() -> str:
    """Access token for the password grant (technical user), cached for its lifetime."""
    client_id = app_config.report_keycloak_client_id
    username = app_config.report_keycloak_username
    return await _cached_token(
        f"password:{client_id}:{username}",
        {
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": app_config.report_keycloak_client_secret,
            "username": username,
            "password": app_config.report_keycloak_password,
        },
    )


async def get_report_service_token() -> str:
    """Client-credentials token — the only kind Raport accepts on its authz endpoint.

    Uses REPORT_SERVICE_CLIENT_ID when set, because the client that serves the password grant is
    typically the public one, and Keycloak answers a public client with
    «Public client not allowed to retrieve service account». The client used here must be
    confidential with service accounts enabled, and listed in Raport's SERVICE_CLIENT_IDS.
    """
    client_id = app_config.report_service_client_id or app_config.report_keycloak_client_id
    return await _cached_token(
        f"client_credentials:{client_id}",
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": app_config.report_service_client_secret or app_config.report_keycloak_client_secret,
        },
    )
