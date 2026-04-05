"""
Unit tests for gateway plugins.

Covers:
  JWT Plugin       : valid token, missing header, invalid signature, expired token,
                     JWKS fetch failure
  API Key Plugin   : missing key → 401, invalid key → 403, valid via header,
                     valid via query param
  Rate Limiter     : Redis allowed, Redis blocked (429), Redis failure → fail open
  Circuit Breaker  : CLOSED passes through, OPEN returns 503,
                     5xx response triggers failure recording
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

from fastapi import Response
from jose import jwt as _jose_jwt
import pytest

from gateway.core.context import AuthMethod, GatewayContext

# Trigger plugin registration
import gateway.plugins.auth.apikey_plugin  # noqa: F401
from gateway.plugins.auth.apikey_plugin import APIKeyPlugin
import gateway.plugins.auth.jwt_plugin  # noqa: F401
from gateway.plugins.auth.jwt_plugin import _JWKS_CACHE, JWTPlugin
import gateway.plugins.circuitbreaker.breaker_plugin  # noqa: F401
from gateway.plugins.circuitbreaker.breaker_plugin import CircuitBreakerPlugin
import gateway.plugins.ratelimit.ratelimit_plugin  # noqa: F401
from gateway.plugins.ratelimit.ratelimit_plugin import _SCRIPT_SHA_CACHE, RateLimiterPlugin

from .conftest import make_request

_JWT_SECRET = "test-secret-key"


# ── helpers ───────────────────────────────────────────────────────────────────

async def _pass_handler(req, ctx) -> Response:
    return Response(status_code=200)


def _make_token(payload: dict, secret: str = _JWT_SECRET, algorithm: str = "HS256") -> str:
    return _jose_jwt.encode(payload, secret, algorithm=algorithm)


# ── JWT Plugin ────────────────────────────────────────────────────────────────

class TestJWTPlugin:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        _JWKS_CACHE.clear()
        yield
        _JWKS_CACHE.clear()

    def _plugin(self, extra_config: dict | None = None) -> JWTPlugin:
        p = JWTPlugin()
        cfg = {"secret_key": _JWT_SECRET, "algorithm": "HS256"}
        if extra_config:
            cfg.update(extra_config)
        p.configure(cfg)
        return p

    async def test_valid_token_passes(self):
        token = _make_token({"sub": "user123", "scope": "read write"})
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()
        resp = await self._plugin()(req, ctx, _pass_handler)
        assert resp.status_code == 200
        assert ctx.principal == "user123"
        assert ctx.auth_method == AuthMethod.JWT
        assert "read" in ctx.scopes

    async def test_missing_header_returns_401(self):
        req = make_request()  # no Authorization header
        ctx = GatewayContext()
        resp = await self._plugin()(req, ctx, _pass_handler)
        assert resp.status_code == 401

    async def test_invalid_signature_returns_401(self):
        token = _make_token({"sub": "user123"}, secret="wrong-secret")
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()
        resp = await self._plugin()(req, ctx, _pass_handler)
        assert resp.status_code == 401

    async def test_expired_token_returns_401(self):
        token = _make_token({"sub": "user123", "exp": int(time.time()) - 3600})
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()
        resp = await self._plugin()(req, ctx, _pass_handler)
        assert resp.status_code == 401

    async def test_error_message_does_not_leak_details(self):
        """JWT validation errors must not expose internal exception text."""
        token = _make_token({"sub": "user123"}, secret="wrong-secret")
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()
        resp = await self._plugin()(req, ctx, _pass_handler)
        assert b"Invalid token" in resp.body
        assert b"JWTError" not in resp.body
        assert b"Signature" not in resp.body

    async def test_jwks_fetch_failure_returns_401(self):
        plugin = self._plugin({"jwks_url": "https://auth.example.com/.well-known/jwks.json"})
        token = _make_token({"sub": "user123"})
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()

        with patch(
            "gateway.plugins.auth.jwt_plugin._fetch_jwks",
            AsyncMock(side_effect=Exception("connection refused")),
        ):
            resp = await plugin(req, ctx, _pass_handler)

        assert resp.status_code == 401

    async def test_scope_parsed_as_space_separated_list(self):
        token = _make_token({"sub": "svc", "scope": "read write admin"})
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()
        await self._plugin()(req, ctx, _pass_handler)
        assert ctx.scopes == ["read", "write", "admin"]

    async def test_audience_is_optional_when_not_configured(self):
        token = _make_token({"sub": "user123", "aud": "gateway"})
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()
        resp = await self._plugin()(req, ctx, _pass_handler)
        assert resp.status_code == 200

    async def test_valid_audience_is_accepted(self):
        token = _make_token({"sub": "user123", "aud": "gateway"})
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()
        resp = await self._plugin({"audience": "gateway"})(req, ctx, _pass_handler)
        assert resp.status_code == 200

    async def test_invalid_issuer_is_rejected(self):
        token = _make_token({"sub": "user123", "iss": "issuer-a"})
        req = make_request(headers={"authorization": f"Bearer {token}"})
        ctx = GatewayContext()
        resp = await self._plugin({"issuer": "issuer-b"})(req, ctx, _pass_handler)
        assert resp.status_code == 401


# ── API Key Plugin ────────────────────────────────────────────────────────────

class TestAPIKeyPlugin:
    def _plugin(self, keys: list[str] | None = None, query_param: str | None = None) -> APIKeyPlugin:
        p = APIKeyPlugin()
        cfg: dict = {"keys": keys or ["valid-key-1", "valid-key-2"]}
        if query_param:
            cfg["query_param"] = query_param
        p.configure(cfg)
        return p

    async def test_missing_key_returns_401(self):
        req = make_request()  # no X-API-Key header
        resp = await self._plugin()(req, GatewayContext(), _pass_handler)
        assert resp.status_code == 401

    async def test_invalid_key_returns_403(self):
        req = make_request(headers={"x-api-key": "wrong-key"})
        resp = await self._plugin()(req, GatewayContext(), _pass_handler)
        assert resp.status_code == 403

    async def test_valid_key_via_header_passes(self):
        req = make_request(headers={"x-api-key": "valid-key-1"})
        ctx = GatewayContext()
        resp = await self._plugin()(req, ctx, _pass_handler)
        assert resp.status_code == 200
        assert ctx.auth_method == AuthMethod.API_KEY

    async def test_valid_key_via_query_param_passes(self):
        # query_string is baked into scope at construction time
        req = make_request(
            path="/api/test",
            query_string=b"_apikey=valid-key-2",
        )
        ctx = GatewayContext()
        resp = await self._plugin(query_param="_apikey")(req, ctx, _pass_handler)
        assert resp.status_code == 200

    async def test_principal_is_truncated_key(self):
        req = make_request(headers={"x-api-key": "valid-key-1"})
        ctx = GatewayContext()
        await self._plugin()(req, ctx, _pass_handler)
        assert ctx.principal.startswith("apikey:")


# ── Rate Limiter Plugin ───────────────────────────────────────────────────────

class TestRateLimiterPlugin:
    @pytest.fixture(autouse=True)
    def _clear_sha_cache(self):
        _SCRIPT_SHA_CACHE.clear()
        yield
        _SCRIPT_SHA_CACHE.clear()

    def _mock_redis(self, evalsha_return: int = 1) -> AsyncMock:
        mock = AsyncMock()
        mock.script_load = AsyncMock(return_value="faksha123")
        mock.evalsha = AsyncMock(return_value=evalsha_return)
        return mock

    def _plugin(self, limit: int = 10, window: int = 60) -> RateLimiterPlugin:
        p = RateLimiterPlugin()
        p.configure({"limit": limit, "window": window, "key_func": "ip"})
        return p

    async def test_allowed_request_passes_through(self):
        mock_redis = self._mock_redis(evalsha_return=1)  # 1 = allowed
        with patch("gateway.plugins.ratelimit.ratelimit_plugin.get_redis", return_value=mock_redis):
            req = make_request(headers={"x-forwarded-for": "10.0.0.1"})
            resp = await self._plugin()(req, GatewayContext(), _pass_handler)
        assert resp.status_code == 200
        mock_redis.evalsha.assert_called_once()

    async def test_blocked_request_returns_429(self):
        mock_redis = self._mock_redis(evalsha_return=0)  # 0 = denied
        with patch("gateway.plugins.ratelimit.ratelimit_plugin.get_redis", return_value=mock_redis):
            req = make_request(headers={"x-forwarded-for": "10.0.0.1"})
            resp = await self._plugin()(req, GatewayContext(), _pass_handler)
        assert resp.status_code == 429
        assert b"Rate limit exceeded" in resp.body

    async def test_retry_after_header_present_on_429(self):
        mock_redis = self._mock_redis(evalsha_return=0)
        with patch("gateway.plugins.ratelimit.ratelimit_plugin.get_redis", return_value=mock_redis):
            req = make_request(headers={"x-forwarded-for": "1.2.3.4"})
            resp = await self._plugin(limit=5, window=30)(req, GatewayContext(), _pass_handler)
        assert resp.status_code == 429
        assert "retry-after" in resp.headers

    async def test_redis_failure_fails_open(self):
        """When Redis is unavailable, traffic must be allowed (fail open)."""
        mock_redis = AsyncMock()
        mock_redis.script_load = AsyncMock(side_effect=Exception("Redis down"))
        with patch("gateway.plugins.ratelimit.ratelimit_plugin.get_redis", return_value=mock_redis):
            req = make_request()
            resp = await self._plugin()(req, GatewayContext(), _pass_handler)
        assert resp.status_code == 200  # fail open

    async def test_script_sha_cached_across_calls(self):
        """script_load must only be called once per Redis client instance."""
        mock_redis = self._mock_redis(evalsha_return=1)
        with patch("gateway.plugins.ratelimit.ratelimit_plugin.get_redis", return_value=mock_redis):
            for _ in range(3):
                plugin = RateLimiterPlugin()
                plugin.configure({"limit": 10, "window": 60})
                await plugin(make_request(), GatewayContext(), _pass_handler)
        # script_load should have been called only once despite 3 plugin executions
        mock_redis.script_load.assert_called_once()


# ── Circuit Breaker Plugin ────────────────────────────────────────────────────

class TestCircuitBreakerPlugin:
    def _plugin(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> CircuitBreakerPlugin:
        p = CircuitBreakerPlugin()
        p.configure({"failure_threshold": failure_threshold, "recovery_timeout": recovery_timeout})
        return p

    def _mock_redis(self, circuit_open: bool = False) -> AsyncMock:
        mock = AsyncMock()
        mock.exists = AsyncMock(return_value=1 if circuit_open else 0)
        mock.ttl = AsyncMock(return_value=25)
        mock.incr = AsyncMock(return_value=1)
        mock.expire = AsyncMock(return_value=True)
        mock.set = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        return mock

    async def test_closed_circuit_passes_request(self):
        mock_redis = self._mock_redis(circuit_open=False)
        with patch("gateway.plugins.circuitbreaker.breaker_plugin.get_redis", return_value=mock_redis):
            resp = await self._plugin()(make_request(), GatewayContext(), _pass_handler)
        assert resp.status_code == 200

    async def test_open_circuit_returns_503(self):
        mock_redis = self._mock_redis(circuit_open=True)
        with patch("gateway.plugins.circuitbreaker.breaker_plugin.get_redis", return_value=mock_redis):
            resp = await self._plugin()(make_request(), GatewayContext(), _pass_handler)
        assert resp.status_code == 503
        assert b"circuit open" in resp.body

    async def test_open_circuit_sets_context_flag(self):
        mock_redis = self._mock_redis(circuit_open=True)
        ctx = GatewayContext()
        with patch("gateway.plugins.circuitbreaker.breaker_plugin.get_redis", return_value=mock_redis):
            await self._plugin()(make_request(), ctx, _pass_handler)
        assert ctx.circuit_open is True

    async def test_5xx_response_records_failure(self):
        mock_redis = self._mock_redis(circuit_open=False)
        mock_redis.incr = AsyncMock(return_value=1)  # first failure

        async def failing_handler(req, ctx):
            return Response(status_code=503)

        with patch("gateway.plugins.circuitbreaker.breaker_plugin.get_redis", return_value=mock_redis):
            await self._plugin()(make_request(), GatewayContext(), failing_handler)

        mock_redis.incr.assert_called_once()

    async def test_2xx_response_does_not_record_failure(self):
        mock_redis = self._mock_redis(circuit_open=False)

        with patch("gateway.plugins.circuitbreaker.breaker_plugin.get_redis", return_value=mock_redis):
            await self._plugin()(make_request(), GatewayContext(), _pass_handler)

        mock_redis.incr.assert_not_called()

    async def test_trips_circuit_when_threshold_reached(self):
        mock_redis = self._mock_redis(circuit_open=False)
        mock_redis.incr = AsyncMock(return_value=3)  # 3rd failure = threshold

        async def failing_handler(req, ctx):
            return Response(status_code=500)

        with patch("gateway.plugins.circuitbreaker.breaker_plugin.get_redis", return_value=mock_redis):
            await self._plugin(failure_threshold=3)(make_request(), GatewayContext(), failing_handler)

        # Circuit should be tripped: open_key set with recovery_timeout
        mock_redis.set.assert_called_once()
