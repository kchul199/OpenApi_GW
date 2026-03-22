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
import urllib.request
import json
from functools import lru_cache

from fastapi import Request, Response
from jose import JWTError, jwt

from gateway.core.context import AuthMethod, GatewayContext
from gateway.plugins.base import BasePlugin, NextFunc, PluginRegistry

logger = logging.getLogger(__name__)


@PluginRegistry.register
class JWTPlugin(BasePlugin):
    name = "jwt-validator"
    order = 10

    def configure(self, config: dict) -> None:
        self._secret: str     = config.get("secret_key", "changeme")
        self._jwks_url: str   = config.get("jwks_url", "")
        self._algorithm: str  = config.get("algorithm", "HS256")
        self._audience: str | None = config.get("audience")
        self._issuer: str | None   = config.get("issuer")
        self._header_name: str     = config.get("header_name", "authorization")

    async def __call__(self, request: Request, ctx: GatewayContext, next: NextFunc) -> Response:
        token = self._extract_token(request)
        if not token:
            return _unauthorized("Missing or invalid Authorization header")

        # Determine key to use (JWKS or secret)
        key_to_use = self._secret
        if self._jwks_url:
            try:
                # Basic sync fetch for simplicity, usually done async and cached
                jwks = self._fetch_jwks(self._jwks_url)
                # python-jose can verify token directly with raw JWKS dict
                key_to_use = jwks
            except Exception as e:
                logger.error(f"JWKS Fetch failed: {e}")
                return _unauthorized("Auth provider unavailable")

        try:
            options: dict = {}
            if self._audience:
                options["audience"] = self._audience
            claims = jwt.decode(
                token,
                key_to_use,
                algorithms=[self._algorithm],
                options=options,
            )
        except JWTError as exc:
            logger.warning(f"JWT validation failed: {exc}", extra={"request_id": ctx.request_id})
            return _unauthorized(f"Invalid token: {exc}")

        ctx.auth_method = AuthMethod.JWT
        ctx.principal   = claims.get("sub", "")
        ctx.scopes      = claims.get("scope", "").split() if isinstance(claims.get("scope"), str) else claims.get("scope", [])
        ctx.claims      = dict(claims)

        return await next(request, ctx)

    def _extract_token(self, request: Request) -> str | None:
        header = request.headers.get(self._header_name, "")
        if header.lower().startswith("bearer "):
            return header[7:]
        return None

    @lru_cache(maxsize=1)
    def _fetch_jwks(self, url: str) -> dict:
        """Cached simple fetch of JWKS. In prod, background async fetch is preferred."""
        req = urllib.request.Request(url, headers={'User-Agent': 'OAG/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())


def _unauthorized(detail: str) -> Response:
    return Response(
        content=f'{{"detail":"{detail}"}}',
        status_code=401,
        media_type="application/json",
        headers={"WWW-Authenticate": "Bearer"},
    )
