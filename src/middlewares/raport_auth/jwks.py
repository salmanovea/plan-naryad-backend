"""Local token verification against Keycloak's signing keys.

The point of doing it here rather than asking Raport on every request: a forged or expired token
is rejected without a single outbound call, so garbage traffic never reaches Raport or Keycloak,
and the service keeps working while they are down.

Only the signature and the standard claims are checked here. Who the user is and what they may
do is Raport's answer — see authz.py.
"""

import asyncio
import json
from typing import Any, Optional

import httpx
from jwcrypto import jwk
from jwcrypto import jwt as jwcrypto_jwt
from jwcrypto.common import JWException

from src.config.logger import LoggerProvider
from src.middlewares.raport_auth.settings import AuthSettings, auth_settings

log = LoggerProvider().get_logger(__name__)

# Anything the header of a Bearer may carry: jwcrypto raises JWException for a token it
# understands and refuses, but a plain ValueError/TypeError for one it cannot even parse
# («Token format unrecognized»). Both mean the same thing to us — 401, not 500.
_DECODE_ERRORS = (JWException, ValueError, TypeError, UnicodeDecodeError)


class TokenInvalid(Exception):
    """The token is not something this realm issued, or it has expired."""


class KeycloakUnavailable(Exception):
    """The signing keys could not be fetched."""


class JWKSCache:
    """Keycloak's public keys, refreshed on expiry and on an unknown `kid`."""

    def __init__(self, settings: AuthSettings = auth_settings) -> None:
        self._settings = settings
        self._keys: Optional[jwk.JWKSet] = None
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self, force: bool = False) -> jwk.JWKSet:
        loop = asyncio.get_running_loop()
        if not force and self._keys is not None and loop.time() - self._fetched_at < self._settings.auth_jwks_ttl:
            return self._keys

        async with self._lock:
            # Another coroutine may have refreshed while we waited for the lock.
            fresh = self._keys is not None and loop.time() - self._fetched_at < self._settings.auth_jwks_ttl
            if not force and fresh:
                return self._keys  # type: ignore[return-value]
            self._keys = await self._fetch()
            self._fetched_at = loop.time()
            return self._keys

    async def _fetch(self) -> jwk.JWKSet:
        url = self._settings.jwks_url
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.auth_timeout,
                verify=self._settings.keycloak_verify_ssl,
            ) as http:
                response = await http.get(url)
        except httpx.HTTPError as e:
            raise KeycloakUnavailable(f"cannot reach Keycloak at {url}: {e}")

        if response.status_code != 200:
            raise KeycloakUnavailable(f"Keycloak returned {response.status_code} for {url}")

        try:
            return jwk.JWKSet.from_json(response.text)
        except (JWException, ValueError) as e:
            raise KeycloakUnavailable(f"Keycloak returned an unusable JWKS: {e}")

    def reset(self) -> None:
        """Forget the cached keys — used by tests."""
        self._keys = None
        self._fetched_at = 0.0


jwks_cache = JWKSCache()


async def verify_token(token: str, settings: AuthSettings = auth_settings, cache: JWKSCache = jwks_cache) -> dict:
    """Return the token's claims, or raise.

    Raises `TokenInvalid` when the token is not acceptable and `KeycloakUnavailable` when that
    cannot be decided — the two lead to different HTTP codes (401 vs 503), and conflating them
    would either hide an outage or lock everybody out during one.
    """
    keys = await cache.get()
    try:
        claims = _decode(token, keys)
    except jwcrypto_jwt.JWTMissingKey:
        # Either the realm rotated its keys or the signature is forged; a refresh tells us which.
        keys = await cache.get(force=True)
        try:
            claims = _decode(token, keys)
        except _DECODE_ERRORS as e:
            raise TokenInvalid(str(e))
    except _DECODE_ERRORS as e:
        raise TokenInvalid(str(e))

    _check_claims(claims, settings)
    return claims


def _decode(token: str, keys: jwk.JWKSet) -> dict:
    verified = jwcrypto_jwt.JWT(jwt=token, key=keys)
    claims: dict = json.loads(verified.claims)
    return claims


def _check_claims(claims: dict, settings: AuthSettings) -> None:
    """`exp` and `nbf` are already enforced by jwcrypto; `iss` and `aud` are ours to check."""
    issuer = claims.get("iss")
    if issuer != settings.issuer:
        raise TokenInvalid(f"unexpected issuer {issuer!r}")

    expected_audience = settings.auth_expected_audience
    if expected_audience:
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if expected_audience not in audiences:
            raise TokenInvalid(f"token is not intended for {expected_audience!r}")


def keycloak_id_from(claims: dict[str, Any]) -> Optional[str]:
    """The id Raport stores in `User.keylock_id`.

    Mirrors `megashablon/src/middlewares/keycloak_middleware.py`: internal users are identified by
    the `fsk_id` claim when FSKPro issues the token, everyone else by `sub`. If the two rules ever
    diverge, nobody can log in — hence the single place here.
    """
    return claims.get("fsk_id") or claims.get("sub")
