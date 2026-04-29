"""
Keycloak password-grant token fetcher for the Raport service account.

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


async def get_report_access_token() -> str:
    """Fetch an access token from Keycloak using the password grant."""
    server_url = (app_config.keycloak_server_url or "").rstrip("/")
    realm = app_config.keycloak_realm

    if not server_url or not realm:
        raise ReportAuthError("KEYCLOAK_SERVER_URL and KEYCLOAK_REALM must be set")

    token_url = server_url + _TOKEN_PATH.format(realm=realm)
    payload = {
        "grant_type": "password",
        "client_id": app_config.report_keycloak_client_id,
        "client_secret": app_config.report_keycloak_client_secret,
        "username": app_config.report_keycloak_username,
        "password": app_config.report_keycloak_password,
    }

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
