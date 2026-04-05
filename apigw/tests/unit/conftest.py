"""
Shared test fixtures and helpers for unit tests.
"""
from __future__ import annotations

import pytest
from starlette.requests import Request

from gateway.config.loader import (
    GRPCProxyConfig,
    MatchConfig,
    PluginConfig,
    RetryConfig,
    RouteConfig,
    UpstreamConfig,
    UpstreamTarget,
    WebSocketProxyConfig,
)
from gateway.core.context import GatewayContext

# ── Request factory ───────────────────────────────────────────────────────────

def make_request(
    method: str = "GET",
    path: str = "/api/test",
    headers: dict[str, str] | None = None,
    query_string: bytes = b"",
    body: bytes = b"",
    client: tuple[str, int] = ("127.0.0.1", 12345),
) -> Request:
    """Build a minimal Starlette Request for tests."""
    _body = body

    async def receive():
        return {"type": "http.request", "body": _body, "more_body": False}

    header_list = [
        (k.lower().encode(), v.encode())
        for k, v in (headers or {}).items()
    ]

    scope = {
        "type": "http",
        "method": method.upper(),
        "path": path,
        "query_string": query_string,
        "headers": header_list,
        "server": ("testserver", 8080),
        "client": client,
        "root_path": "",
        "scheme": "http",
    }
    return Request(scope, receive)


# ── Route factory ─────────────────────────────────────────────────────────────

def make_route(
    id: str = "test-route",
    protocol: str = "HTTP",
    path: str = "/api/**",
    methods: list[str] | None = None,
    host: str | None = None,
    match_headers: dict[str, str] | None = None,
    upstream_url: str = "http://backend:8000",
    load_balance: str = "round_robin",
    hash_on: str = "client_ip",
    hash_key: str | None = None,
    plugins: list[PluginConfig] | None = None,
    strip_prefix: bool = False,
    preserve_host: bool = False,
    retry_count: int = 0,
    upstream_targets: list[tuple[str, int]] | None = None,
    upstream_type: str = "REST",
    grpc_cardinality: str = "unary_unary",
    websocket_forward_headers: list[str] | None = None,
) -> RouteConfig:
    """Build a RouteConfig with sensible defaults."""
    if upstream_targets:
        targets = [UpstreamTarget(url=u, weight=w) for u, w in upstream_targets]
    else:
        targets = [UpstreamTarget(url=upstream_url, weight=100)]

    return RouteConfig(
        id=id,
        match=MatchConfig(
            protocol=protocol,
            path=path,
            methods=methods or ["GET", "POST", "PUT", "DELETE", "PATCH"],
            host=host,
            headers=match_headers or {},
        ),
        upstream=UpstreamConfig(
            type=upstream_type,
            targets=targets,
            load_balance=load_balance,
            retry=RetryConfig(count=retry_count),
            hash_on=hash_on,
            hash_key=hash_key,
        ),
        grpc=GRPCProxyConfig(cardinality=grpc_cardinality),
        websocket=WebSocketProxyConfig(forward_headers=websocket_forward_headers or []),
        plugins=plugins or [],
        strip_prefix=strip_prefix,
        preserve_host=preserve_host,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ctx() -> GatewayContext:
    c = GatewayContext()
    c.request_id = "test-request-id"
    return c
