"""
Built-in plugins:
  - RequestIDPlugin  : Injects X-Request-ID into context and response
  - LoggingPlugin    : Structured request/response logging
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request, Response

from gateway.core.context import GatewayContext
from gateway.plugins.base import BasePlugin, NextFunc, PluginRegistry

logger = logging.getLogger(__name__)


@PluginRegistry.register
class RequestIDPlugin(BasePlugin):
    """
    Ensures every request has a unique X-Request-ID.
    If the client provides one, it is reused; otherwise one is generated.
    """

    name = "request-id"
    order = 1

    async def __call__(self, request: Request, ctx: GatewayContext, next: NextFunc) -> Response:
        client_id = request.headers.get("x-request-id")
        if client_id:
            ctx.request_id = client_id

        response = await next(request, ctx)
        response.headers["X-Request-ID"] = ctx.request_id
        return response


@PluginRegistry.register
class LoggingPlugin(BasePlugin):
    """
    Structured request/response logger.
    Config keys:
      log_headers (bool): include request headers in log, default False
      log_body    (bool): include request body snippet, default False
    """

    name = "access-logger"
    order = 2

    def configure(self, config: dict[str, Any]) -> None:
        self._log_headers: bool = config.get("log_headers", False)
        self._log_body: bool = config.get("log_body", False)

    async def __call__(self, request: Request, ctx: GatewayContext, next: NextFunc) -> Response:
        start = time.monotonic()

        extra: dict[str, Any] = {
            "request_id": ctx.request_id,
            "method": request.method,
            "path": request.url.path,
            "remote_addr": request.client.host if request.client else "-",
        }
        if self._log_headers:
            extra["headers"] = dict(request.headers)

        try:
            response = await next(request, ctx)
        except Exception as exc:
            logger.error("Request failed", extra={**extra, "error": str(exc)})
            raise

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Request handled",
            extra={
                **extra,
                "status": response.status_code,
                "duration_ms": round(elapsed_ms, 2),
                "route_id": ctx.route_id,
                "principal": ctx.principal or "-",
            },
        )
        return response
