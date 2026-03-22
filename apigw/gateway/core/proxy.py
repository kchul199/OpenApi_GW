"""
Async HTTP Reverse Proxy using httpx.
Streams requests to upstream and returns responses transparently.
Supports timeout, retry (via tenacity), and header forwarding.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import Request, Response
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from gateway.config.loader import RouteConfig
from gateway.core.context import GatewayContext

logger = logging.getLogger(__name__)

# Hop-by-hop headers that must not be forwarded
HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


def _filter_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}


class HTTPReverseProxy:
    """
    Async reverse proxy for HTTP/HTTPS upstreams.
    Uses a shared httpx.AsyncClient with connection pooling.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._client: httpx.AsyncClient | None = None
        self._default_timeout = timeout

    async def startup(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._default_timeout),
            limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
            follow_redirects=False,
            verify=True,
        )
        logger.info("HTTP Reverse Proxy client started")

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            logger.info("HTTP Reverse Proxy client closed")

    async def proxy(
        self,
        request: Request,
        ctx: GatewayContext,
        route: RouteConfig,
    ) -> Response:
        """Forward the request to the resolved upstream target."""
        if ctx.upstream is None:
            return Response(content='{"detail":"No upstream resolved"}', status_code=502, media_type="application/json")
        if self._client is None:
            return Response(content='{"detail":"Proxy not initialized"}', status_code=503, media_type="application/json")

        upstream_url = self._build_url(ctx.upstream.url, request, route)
        req_headers = _filter_headers(dict(request.headers))

        # Forwarding headers
        req_headers["X-Forwarded-For"]   = request.client.host if request.client else "unknown"
        req_headers["X-Request-ID"]      = ctx.request_id
        req_headers["X-Gateway-Route"]   = ctx.route_id
        if not route.preserve_host:
            req_headers.pop("host", None)

        body = await request.body()

        try:
            upstream_response = await self._send_with_retry(
                method=request.method,
                url=upstream_url,
                headers=req_headers,
                content=body,
                timeout=route.upstream.timeout,
                retry_cfg=route.upstream.retry,
            )
        except httpx.TimeoutException:
            logger.warning(f"Upstream timeout: {upstream_url}", extra={"route": ctx.route_id})
            return Response(content='{"detail":"Upstream timeout"}', status_code=504, media_type="application/json")
        except httpx.ConnectError:
            logger.error(f"Upstream connection failed: {upstream_url}", extra={"route": ctx.route_id})
            return Response(content='{"detail":"Upstream unavailable"}', status_code=502, media_type="application/json")

        resp_headers = _filter_headers(dict(upstream_response.headers))
        resp_headers["X-Request-ID"] = ctx.request_id

        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=resp_headers,
            media_type=upstream_response.headers.get("content-type"),
        )

    def _build_url(self, base: str, request: Request, route: RouteConfig) -> str:
        path = request.url.path
        if route.strip_prefix:
            prefix = route.match.path.rstrip("/**").rstrip("*")
            path = path[len(prefix):] or "/"
        query = request.url.query
        url = base.rstrip("/") + path
        if query:
            url += "?" + query
        return url

    async def _send_with_retry(
        self, method: str, url: str, headers: dict, content: bytes,
        timeout: float, retry_cfg,
    ) -> httpx.Response:
        assert self._client is not None

        last_exc: Exception | None = None
        for attempt in range(retry_cfg.count + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=content,
                    timeout=timeout,
                )
                if response.status_code not in retry_cfg.status_codes or attempt == retry_cfg.count:
                    return response
                logger.warning(
                    f"Retrying upstream (attempt {attempt+1}): status={response.status_code}"
                )
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt == retry_cfg.count:
                    break
                logger.warning(f"Retrying upstream due to {exc.__class__.__name__} (attempt {attempt+1})")

            import asyncio
            wait = retry_cfg.backoff_factor * (2 ** attempt)
            await asyncio.sleep(wait)

        if last_exc:
            raise last_exc
        raise httpx.RequestError("Retry exhausted")
