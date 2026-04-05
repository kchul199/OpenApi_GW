"""
API Key Authentication Plugin.
Validates API keys from headers or query parameters.

Config keys:
  keys          (list[str])  : list of valid API keys (static list, simple mode)
  header_name   (str)        : default "X-API-Key"
  query_param   (str|None)   : also accept key in this query param
  redis_prefix  (str)        : Redis key prefix for dynamic key lookup
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request, Response

from gateway.core.context import AuthMethod, GatewayContext
from gateway.plugins.base import BasePlugin, NextFunc, PluginRegistry

logger = logging.getLogger(__name__)


@PluginRegistry.register
class APIKeyPlugin(BasePlugin):
    name = "api-key"
    order = 11

    def configure(self, config: dict[str, Any]) -> None:
        self._keys: set[str] = set(config.get("keys", []))
        self._header_name: str = config.get("header_name", "x-api-key")
        self._query_param: str | None = config.get("query_param")

    async def __call__(self, request: Request, ctx: GatewayContext, next: NextFunc) -> Response:
        key = self._extract_key(request)
        if not key:
            return _unauthorized("API Key missing")
        if key not in self._keys:
            logger.warning("Invalid API Key", extra={"request_id": ctx.request_id})
            return _forbidden("Invalid API Key")

        ctx.auth_method = AuthMethod.API_KEY
        ctx.principal = f"apikey:{key[:8]}…"
        return await next(request, ctx)

    def _extract_key(self, request: Request) -> str | None:
        key = request.headers.get(self._header_name)
        if not key and self._query_param:
            key = request.query_params.get(self._query_param)
        return key


def _unauthorized(detail: str) -> Response:
    return Response(
        content=f'{{"detail":"{detail}"}}',
        status_code=401,
        media_type="application/json",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def _forbidden(detail: str) -> Response:
    return Response(
        content=f'{{"detail":"{detail}"}}',
        status_code=403,
        media_type="application/json",
    )
