"""Authentication against Keycloak's keys plus Raport's permission model.

The cases here are the ones a plausible-looking implementation gets wrong: a forged token that
carries a valid `kid`, an expired one, a user whose groups do not match, an outage that must not
be mistaken for a refusal, and a cache that outlives the token it was built from.
"""

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from jwcrypto import jwk
from jwcrypto import jwt as jwcrypto_jwt
from starlette.authentication import AuthenticationError
from starlette.requests import HTTPConnection

from src.middlewares.raport_auth.backend import RaportAuthBackend, ServiceUser
from src.middlewares.raport_auth.jwks import JWKSCache, TokenInvalid, keycloak_id_from, verify_token
from src.middlewares.raport_auth.settings import AuthSettings, validate_auth_settings

ISSUER = "https://keycloak.test/realms/fsk"
USER = {
    "id": "0f1b0000-0000-0000-0000-000000000001",
    "keylock_id": "kc-1",
    "shown_name": "Иванов И.И.",
    "email": "i@fsk.ru",
    "is_active": True,
    "is_admin": False,
    "groups": ["smr_management_user", "plan_naryad"],
}

_realm_key = jwk.JWK.generate(kty="RSA", size=2048, kid="realm-key", alg="RS256", use="sig")
_other_key = jwk.JWK.generate(kty="RSA", size=2048, kid="realm-key", alg="RS256", use="sig")


def make_token(key: jwk.JWK = _realm_key, **overrides) -> str:
    claims = {
        "sub": "kc-1",
        "iss": ISSUER,
        "exp": int(time.time()) + 300,
        "azp": "report-front-client",
        **overrides,
    }
    token = jwcrypto_jwt.JWT(header={"alg": "RS256", "kid": key.kid}, claims=claims)
    token.make_signed_token(key)
    return token.serialize()


def make_settings(**overrides) -> AuthSettings:
    defaults = {
        "auth_enabled": True,
        "auth_allowed_groups": "superuser,plan_naryad",
        "auth_service_clients": "",
        "auth_authz_mode": "users-me",
        "keycloak_server_url": "https://keycloak.test",
        "keycloak_realm": "fsk",
        "report_api_url": "https://raport.test",
        "auth_expected_audience": None,
    }
    return AuthSettings(**{**defaults, **overrides})


def make_jwks(key: jwk.JWK = _realm_key) -> JWKSCache:
    """A key cache preloaded with the realm's public key — no network in the tests."""
    key_set = jwk.JWKSet()
    key_set.add(key)
    public = jwk.JWKSet.from_json(key_set.export(private_keys=False))

    cache = JWKSCache()
    cache._fetch = AsyncMock(return_value=public)  # type: ignore[method-assign]
    return cache


def make_conn(path: str = "/api/plan-naryad/", token: str | None = None, method: str = "GET") -> HTTPConnection:
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return HTTPConnection({"type": "http", "method": method, "path": path, "headers": headers})


def make_backend(settings: AuthSettings | None = None, jwks: JWKSCache | None = None, **kwargs) -> RaportAuthBackend:
    return RaportAuthBackend(settings=settings or make_settings(), jwks=jwks or make_jwks(), **kwargs)


def mock_raport(status_code: int = 200, payload=USER):
    response = httpx.Response(status_code, json=payload, request=httpx.Request("GET", "https://raport.test"))
    return patch("httpx.AsyncClient.get", AsyncMock(return_value=response))


class TestVerifyToken:
    async def test_accepts_a_token_this_realm_signed(self):
        claims = await verify_token(make_token(), make_settings(), make_jwks())
        assert claims["sub"] == "kc-1"

    async def test_rejects_an_expired_token(self):
        with pytest.raises(TokenInvalid):
            await verify_token(make_token(exp=int(time.time()) - 3600), make_settings(), make_jwks())

    async def test_rejects_a_forged_signature_under_a_valid_kid(self):
        # Same `kid` as the realm key, different private key — the signature must still fail.
        with pytest.raises(TokenInvalid):
            await verify_token(make_token(key=_other_key), make_settings(), make_jwks())

    @pytest.mark.parametrize(
        "garbage",
        ["garbage", "", "a.b", "not.a.jwt", "eyJhbGciOiJSUzI1NiIsImtpZCI6IngifQ.eyJzdWIiOiJ1In0.sig"],
        ids=["word", "empty", "two-parts", "three-parts", "valid-shape-broken-payload"],
    )
    async def test_rejects_anything_that_is_not_a_token(self, garbage):
        # jwcrypto raises a plain ValueError for a token it cannot parse — if that escapes,
        # a random string in the Authorization header turns into a 500.
        with pytest.raises(TokenInvalid):
            await verify_token(garbage, make_settings(), make_jwks())

    async def test_rejects_a_foreign_issuer(self):
        with pytest.raises(TokenInvalid):
            await verify_token(make_token(iss="https://evil.test/realms/fsk"), make_settings(), make_jwks())

    async def test_audience_is_checked_only_when_configured(self):
        settings = make_settings(auth_expected_audience="plan-naryad")
        with pytest.raises(TokenInvalid):
            await verify_token(make_token(), settings, make_jwks())

        claims = await verify_token(make_token(aud=["plan-naryad", "account"]), settings, make_jwks())
        assert claims["sub"] == "kc-1"

    async def test_unknown_kid_triggers_one_key_refresh(self):
        jwks = make_jwks()
        with pytest.raises(TokenInvalid):
            await verify_token(make_token(key=_other_key), make_settings(), jwks)
        # First call plus the forced refresh — a rotated realm key must be picked up.
        assert jwks._fetch.await_count == 2


class TestKeycloakId:
    def test_fsk_id_wins_over_sub_for_internal_users(self):
        assert keycloak_id_from({"sub": "s", "fsk_id": "f"}) == "f"

    def test_falls_back_to_sub(self):
        assert keycloak_id_from({"sub": "s"}) == "s"
        assert keycloak_id_from({}) is None


class TestAuthenticate:
    async def test_authenticates_a_user_with_an_allowed_group(self):
        with mock_raport():
            credentials, user = await make_backend().authenticate(make_conn(token=make_token()))
        assert "authenticated" in credentials.scopes
        assert user.display_name == "Иванов И.И."

    async def test_401_without_a_header(self):
        with pytest.raises(AuthenticationError) as e:
            await make_backend().authenticate(make_conn())
        assert e.value.status_code == 401

    async def test_401_for_an_expired_token_without_calling_raport(self):
        with mock_raport() as get:
            with pytest.raises(AuthenticationError) as e:
                await make_backend().authenticate(make_conn(token=make_token(exp=int(time.time()) - 60)))
        assert e.value.status_code == 401
        # The whole point of verifying locally: garbage never reaches Raport.
        assert get.call_count == 0

    async def test_403_for_a_user_outside_the_allowed_groups(self):
        with mock_raport(200, {**USER, "groups": ["factgathering_user"]}):
            with pytest.raises(AuthenticationError) as e:
                await make_backend().authenticate(make_conn(token=make_token()))
        assert e.value.status_code == 403

    async def test_403_for_a_user_raport_marks_inactive(self):
        with mock_raport(200, {**USER, "is_active": False}):
            with pytest.raises(AuthenticationError) as e:
                await make_backend().authenticate(make_conn(token=make_token()))
        assert e.value.status_code == 403

    async def test_missing_is_active_does_not_block(self):
        # /users/me carries no such flag; absent must not read as False.
        payload = {key: value for key, value in USER.items() if key != "is_active"}
        with mock_raport(200, payload):
            _, user = await make_backend().authenticate(make_conn(token=make_token()))
        assert user.is_authenticated

    async def test_403_when_raport_does_not_know_the_user(self):
        with mock_raport(404, {"error": "not found"}):
            with pytest.raises(AuthenticationError) as e:
                await make_backend().authenticate(make_conn(token=make_token()))
        assert e.value.status_code == 403

    async def test_503_when_raport_is_unreachable(self):
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=httpx.ConnectError("refused"))):
            with pytest.raises(AuthenticationError) as e:
                await make_backend().authenticate(make_conn(token=make_token()))
        assert e.value.status_code == 503

    async def test_503_when_keycloak_keys_cannot_be_fetched(self):
        from src.middlewares.raport_auth.jwks import KeycloakUnavailable

        jwks = make_jwks()
        jwks._fetch = AsyncMock(side_effect=KeycloakUnavailable("down"))  # type: ignore[method-assign]
        with pytest.raises(AuthenticationError) as e:
            await make_backend(jwks=jwks).authenticate(make_conn(token=make_token()))
        assert e.value.status_code == 503

    async def test_service_client_skips_the_group_check(self):
        settings = make_settings(auth_service_clients="raport-scheduler")
        with mock_raport() as get:
            credentials, user = await make_backend(settings).authenticate(
                make_conn(token=make_token(azp="raport-scheduler"))
            )
        assert isinstance(user, ServiceUser)
        assert "service" in credentials.scopes
        assert user.display_name == "raport-scheduler"
        # No Raport user behind a service client — anything expecting a UUID here would break.
        assert user.data["id"] is None
        # A machine caller has no Raport profile to fetch.
        assert get.call_count == 0

    async def test_public_routes_and_preflight_skip_the_check(self):
        backend = make_backend(public_route_prefixes=("/pn/admin",))
        assert await backend.authenticate(make_conn(path="/health")) is None
        assert await backend.authenticate(make_conn(path="/pn/admin/housing/list")) is None
        assert await backend.authenticate(make_conn(method="OPTIONS")) is None

    async def test_disabled_auth_lets_everything_through(self):
        backend = make_backend(make_settings(auth_enabled=False))
        assert await backend.authenticate(make_conn()) is None


class TestAuthzMode:
    """Contract with Raport's GET /api/v1/authz/users/{keycloak_id} (UserAuthzSchema)."""

    # Exactly what megashablon/src/api/routes/authz/schemes.py returns.
    PAYLOAD = {
        "id": "0f1b0000-0000-0000-0000-000000000001",
        "keylock_id": "kc-1",
        "shown_name": "Иванов И.И.",
        "first_name": "Иван",
        "last_name": "Иванов",
        "middle_name": "Иванович",
        "email": "i@fsk.ru",
        "is_active": True,
        "is_admin": False,
        "is_external": False,
        "groups": ["smr_management_user", "plan_naryad"],
        "projects": [{"id": "p-1", "name": "Проект"}],
        "contractors": [{"id": "c-1", "name": "Подрядчик"}],
    }

    def backend(self):
        settings = make_settings(auth_authz_mode="authz")
        return RaportAuthBackend(
            settings=settings,
            jwks=make_jwks(),
            service_token_provider=AsyncMock(return_value="service-token"),
        )

    async def test_reads_the_authz_answer(self):
        with mock_raport(200, self.PAYLOAD) as get:
            _, user = await self.backend().authenticate(make_conn(token=make_token()))

        assert user.display_name == "Иванов И.И."
        assert user.groups == {"smr_management_user", "plan_naryad"}
        assert user.data["is_active"] is True
        # By user id, with the service token — not the user's own.
        url, kwargs = get.await_args.args[0], get.await_args.kwargs
        assert url == "https://raport.test/api/v1/authz/users/kc-1"
        assert kwargs["headers"]["Authorization"] == "Bearer service-token"

    async def test_unknown_user_is_403_not_500(self):
        with mock_raport(404, {"detail": {"message": "User not found"}}):
            with pytest.raises(AuthenticationError) as e:
                await self.backend().authenticate(make_conn(token=make_token()))
        assert e.value.status_code == 403

    async def test_refused_service_token_is_503_not_403(self):
        # Raport answering 401/403 means our client is not whitelisted — a misconfiguration.
        # Reporting it as «you have no access» would mislead every user and poison the cache.
        for status_code in (401, 403):
            with mock_raport(status_code, {"code": str(status_code), "message": "service client required"}):
                with pytest.raises(AuthenticationError) as e:
                    await self.backend().authenticate(make_conn(token=make_token()))
            assert e.value.status_code == 503

    async def test_503_when_the_service_token_cannot_be_obtained(self):
        backend = RaportAuthBackend(
            settings=make_settings(auth_authz_mode="authz"),
            jwks=make_jwks(),
            service_token_provider=AsyncMock(side_effect=RuntimeError("keycloak down")),
        )
        with pytest.raises(AuthenticationError) as e:
            await backend.authenticate(make_conn(token=make_token()))
        assert e.value.status_code == 503


class TestCache:
    async def test_second_request_of_the_same_user_does_not_hit_raport(self):
        backend = make_backend()
        with mock_raport() as get:
            await backend.authenticate(make_conn(token=make_token()))
            await backend.authenticate(make_conn(token=make_token()))
        # Keyed by user, not by token: a refreshed token reuses the same answer.
        assert get.call_count == 1

    async def test_a_refusal_is_cached_too(self):
        backend = make_backend()
        with mock_raport(200, {**USER, "groups": ["factgathering_user"]}) as get:
            for _ in range(3):
                with pytest.raises(AuthenticationError) as e:
                    await backend.authenticate(make_conn(token=make_token()))
                assert e.value.status_code == 403
        assert get.call_count == 1

    async def test_the_entry_never_outlives_the_token(self):
        backend = make_backend()
        # Token dies in a second, the configured TTL is two minutes — the earlier one must win.
        token = make_token(exp=int(time.time()) + 1)
        with mock_raport():
            await backend.authenticate(make_conn(token=token))
        assert backend._ttl_for({"exp": time.time() + 1}) <= 1

    async def test_an_already_expired_token_is_not_cached(self):
        backend = make_backend()
        assert backend._ttl_for({"exp": time.time() - 5}) == 0


class TestActor:
    """Audit fields store the Keycloak id, never a name — names are personal data (152-ФЗ)."""

    def request_with(self, user) -> HTTPConnection:
        conn = HTTPConnection({"type": "http", "method": "GET", "path": "/", "headers": []})
        conn.scope["user"] = user
        return conn

    def test_a_user_is_recorded_by_keycloak_id_not_by_name(self):
        from src.middlewares.raport_auth.backend import RaportUser
        from src.services.common import current_actor

        user = RaportUser({"shown_name": "Иванов И.И."}, claims={"sub": "kc-1", "fsk_id": "fsk-9"})
        assert current_actor(self.request_with(user)) == "fsk-9"
        assert "Иванов" not in current_actor(self.request_with(user))

    def test_sub_is_the_fallback_id(self):
        from src.middlewares.raport_auth.backend import RaportUser
        from src.services.common import current_actor

        user = RaportUser({"shown_name": "Иванов И.И."}, claims={"sub": "kc-1"})
        assert current_actor(self.request_with(user)) == "kc-1"

    def test_a_service_caller_is_recorded_by_client_id(self):
        from src.services.common import current_actor

        assert current_actor(self.request_with(ServiceUser("raport-scheduler"))) == "raport-scheduler"

    def test_nobody_is_recorded_as_system(self):
        from src.services.common import current_actor

        conn = HTTPConnection({"type": "http", "method": "GET", "path": "/", "headers": []})
        assert current_actor(conn) == "system"


class TestSettingsIsolation:
    """The auth block owns its AUTH_* variables; the service config must tolerate them."""

    def test_app_config_ignores_variables_owned_by_other_blocks(self, monkeypatch):
        # Reproduces a real startup crash: with AUTH_* in .env, AppConfig(extra='forbid')
        # refused to build and the service would not start at all.
        from src.config.settings import AppConfig

        monkeypatch.setenv("AUTH_ALLOWED_GROUPS", "superuser")
        monkeypatch.setenv("AUTH_AUTHZ_MODE", "authz")
        monkeypatch.setenv("SOME_OTHER_BLOCK_SETTING", "x")
        assert AppConfig().project_title


class TestSettingsValidation:
    def test_empty_group_list_is_a_startup_error(self):
        with pytest.raises(RuntimeError, match="AUTH_ALLOWED_GROUPS"):
            validate_auth_settings(make_settings(auth_allowed_groups=""))

    def test_missing_keycloak_or_raport_is_a_startup_error(self):
        with pytest.raises(RuntimeError, match="KEYCLOAK_SERVER_URL"):
            validate_auth_settings(make_settings(keycloak_server_url=None))
        with pytest.raises(RuntimeError, match="REPORT_API_URL"):
            validate_auth_settings(make_settings(report_api_url=None))

    def test_unknown_authz_mode_is_a_startup_error(self):
        with pytest.raises(RuntimeError, match="AUTH_AUTHZ_MODE"):
            validate_auth_settings(make_settings(auth_authz_mode="magic"))

    def test_disabled_auth_needs_no_configuration(self):
        validate_auth_settings(make_settings(auth_enabled=False, auth_allowed_groups="", report_api_url=None))
