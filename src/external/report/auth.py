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

Copied into src/external/report/auth.py by the report-microservice skill.
No caching on purpose — every request obtains a fresh access token.
"""

import httpx

from src.config.logger import LoggerProvider
from src.config.settings import app_config

log = LoggerProvider().get_logger(__name__)

_TOKEN_PATH = "/realms/{realm}/protocol/openid-connect/token"


class ReportAuthError(RuntimeError):
    """Raised when the Raport service account fails to obtain an access token."""


async def _fetch_token(payload: dict[str, str | None]) -> str:
    server_url = (app_config.keycloak_server_url or "").rstrip("/")
    realm = app_config.keycloak_realm

    if not server_url or not realm:
        raise ReportAuthError("KEYCLOAK_SERVER_URL and KEYCLOAK_REALM must be set")

    token_url = server_url + _TOKEN_PATH.format(realm=realm)

    async with httpx.AsyncClient(
        timeout=10.0,
        verify=app_config.keycloak_verify_ssl,
    ) as http:
        response = await http.post(token_url, data=payload)

    if response.status_code != 200:
        log.error(f"Report Keycloak token request failed: status={response.status_code} body={response.text[:500]}")
        raise ReportAuthError(f"Keycloak returned {response.status_code} while issuing the Raport token")

    token = response.json().get("access_token")
    if not token:
        raise ReportAuthError("Keycloak response did not contain access_token")
    return token


async def get_report_access_token() -> str:
    """Fetch an access token from Keycloak using the password grant (technical user)."""
    return await _fetch_token(
        {
            "grant_type": "password",
            "client_id": app_config.report_keycloak_client_id,
            "client_secret": app_config.report_keycloak_client_secret,
            "username": app_config.report_keycloak_username,
            "password": app_config.report_keycloak_password,
        }
    )


async def get_report_service_token() -> str:
    """Fetch a client-credentials token — the only kind Raport accepts on its authz endpoint.

    Uses REPORT_SERVICE_CLIENT_ID when set, because the client that serves the password grant is
    typically the public one, and Keycloak answers a public client with
    «Public client not allowed to retrieve service account». The client used here must be
    confidential with service accounts enabled, and listed in Raport's SERVICE_CLIENT_IDS.
    """
    return await _fetch_token(
        {
            "grant_type": "client_credentials",
            "client_id": app_config.report_service_client_id or app_config.report_keycloak_client_id,
            "client_secret": app_config.report_service_client_secret or app_config.report_keycloak_client_secret,
        }
    )
