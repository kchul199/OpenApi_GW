"""
JWT Authentication Plugin.
Validates Bearer tokens using python-jose.

Config keys:
  secret_key    (str)       : HMAC secret OR path to PEM public key
  algorithm     (str)       : HS256 | RS256 | ES256  (default: HS256)
  audience      (str|None)  : expected `aud` claim
  issuer        (str|None)  : expected `iss` claim
  header_name   (str)       : default "Authorization"
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import Request, Response
import httpx
from jose import JWTError, jwt

from gateway.core.context import AuthMethod, GatewayContext
from gateway.plugins.base import BasePlugin, NextFunc, PluginRegistry

logger = logging.getLogger(__name__)

# Module-level JWKS cache: url -> JWKS dict
# Survives across multiple plugin instances created per request.
_JWKS_CACHE: dict[str, dict[str, Any]] = {}


async def _fetch_jwks(url: str) -> dict[str, Any]:
    """Async fetch of JWKS endpoint with module-level caching."""
    if url in _JWKS_CACHE:
        return _JWKS_CACHE[url]
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url, headers={"User-Agent": "OAG/1.0"})
        resp.raise_for_status()
        jwks = cast(dict[str, Any], resp.json())
    _JWKS_CACHE[url] = jwks
    return jwks


@PluginRegistry.register
class JWTPlugin(BasePlugin):
    name = "jwt-validator"
    order = 10

    def configure(self, config: dict[str, Any]) -> None:
        self._secret: str | dict[str, Any] = config.get("secret_key", "changeme")
        self._jwks_url: str = config.get("jwks_url", "")
        self._algorithm: str = config.get("algorithm", "HS256")
        self._audience: str | None = config.get("audience")
        self._issuer: str | None = config.get("issuer")
        self._header_name: str = config.get("header_name", "authorization")

    async def __call__(self, request: Request, ctx: GatewayContext, next: NextFunc) -> Response:
        token = self._extract_token(request)
        if not token:
            return _unauthorized("Missing or invalid Authorization header")

        # Determine key to use (JWKS or secret)
        key_to_use: str | dict[str, Any] = self._secret
        if self._jwks_url:
            try:
                jwks = await _fetch_jwks(self._jwks_url)
                # python-jose can verify token directly with raw JWKS dict
                key_to_use = jwks
            except Exception as e:
                logger.error(f"JWKS fetch failed: {e}")
                return _unauthorized("Auth provider unavailable")

        try:
            decode_kwargs: dict[str, object] = {
                "algorithms": [self._algorithm],
            }
            options: dict[str, bool] = {}
            if self._audience:
                decode_kwargs["audience"] = self._audience
            else:
                options["verify_aud"] = False
            if self._issuer:
                decode_kwargs["issuer"] = self._issuer
            if options:
                decode_kwargs["options"] = options
            claims = jwt.decode(
                token,
                key_to_use,
                **decode_kwargs,
            )
        except JWTError as exc:
            logger.warning(f"JWT validation failed: {exc}", extra={"request_id": ctx.request_id})
            return _unauthorized("Invalid token")

        ctx.auth_method = AuthMethod.JWT
        ctx.principal = claims.get("sub", "")
        ctx.scopes = (
            claims.get("scope", "").split()
            if isinstance(claims.get("scope"), str)
            else claims.get("scope", [])
        )
        ctx.claims = dict(claims)

        return await next(request, ctx)

    def _extract_token(self, request: Request) -> str | None:
        header = request.headers.get(self._header_name, "")
        if header.lower().startswith("bearer "):
            return header[7:]
        return None


def _unauthorized(detail: str) -> Response:
    return Response(
        content=f'{{"detail":"{detail}"}}',
        status_code=401,
        media_type="application/json",
        headers={"WWW-Authenticate": "Bearer"},
    )
