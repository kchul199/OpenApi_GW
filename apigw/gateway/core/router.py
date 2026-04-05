"""
Dynamic routing engine.
Matches incoming requests to RouteConfig entries using:
  - Exact match
  - Prefix match  (path ends with /**)
  - Regex match   (path starts with ~)
  - Header-based match

Routes are evaluated in declaration order; first match wins.
"""

from __future__ import annotations

from collections import defaultdict
from fnmatch import fnmatch
import logging
import re

from fastapi import Request

from gateway.config.loader import RouteConfig
from gateway.core.context import GatewayContext, Protocol, UpstreamInfo

logger = logging.getLogger(__name__)


def _protocol_from_request(request: Request) -> Protocol:
    """Detect protocol from request headers."""
    ct = request.headers.get("content-type", "")
    upgrade = request.headers.get("upgrade", "").lower()
    if upgrade == "websocket":
        return Protocol.WEBSOCKET
    if ct.startswith("application/grpc"):
        return Protocol.GRPC
    return Protocol.HTTP


def _match_path(pattern: str, path: str) -> bool:
    """
    Match request path against route pattern.
      /api/v1/users     → exact
      /api/v1/**        → prefix (glob)
      ~/api/v[0-9]+/.*  → regex
    """
    if pattern.startswith("~"):
        return bool(re.fullmatch(pattern[1:], path))
    if "**" in pattern or "*" in pattern:
        return fnmatch(path, pattern)
    return path == pattern


def _match_headers(required: dict[str, str], actual: dict[str, str]) -> bool:
    for key, value in required.items():
        if actual.get(key.lower(), "") != value:
            return False
    return True


class RoutingEngine:
    """
    Matches a request to a registered RouteConfig.

    Call `update_routes()` during hot-reload to atomically replace route table.
    """

    def __init__(self) -> None:
        self._routes: list[RouteConfig] = []
        self._round_robin_counters: dict[str, int] = defaultdict(int)

    def update_routes(self, routes: list[RouteConfig]) -> None:
        self._routes = list(routes)
        active_ids = {route.id for route in routes}
        self._round_robin_counters = defaultdict(
            int,
            {
                route_id: counter
                for route_id, counter in self._round_robin_counters.items()
                if route_id in active_ids
            },
        )
        logger.info(f"Routing table updated: {len(self._routes)} routes")

    def match(self, request: Request) -> RouteConfig | None:
        """Return the first matching RouteConfig, or None."""
        protocol = _protocol_from_request(request)
        path = request.url.path
        method = request.method.upper()
        host = request.headers.get("host", "")
        headers = dict(request.headers)

        for route in self._routes:
            m = route.match

            # Protocol check
            if m.protocol.upper() != protocol.value.upper():
                continue

            # Host check (optional)
            if m.host and m.host not in (host, "*"):
                continue

            # Path check
            if not _match_path(m.path, path):
                continue

            # Method check (gRPC / WS always pass)
            if protocol == Protocol.HTTP and method not in [x.upper() for x in m.methods]:
                continue

            # Header check
            if m.headers and not _match_headers(m.headers, headers):
                continue

            logger.debug(f"Route matched: {route.id} for {method} {path}")
            return route

        logger.debug(f"No route matched for {method} {path}")
        return None

    def match_grpc(
        self,
        path: str,
        host: str = "",
        headers: dict[str, str] | None = None,
    ) -> RouteConfig | None:
        """
        Match a gRPC request directly by path/host/headers.
        Used by GenericGRPCProxy which does not have a Starlette Request object.
        """
        headers = headers or {}
        for route in self._routes:
            m = route.match
            if m.protocol.upper() != Protocol.GRPC.value.upper():
                continue
            if m.host and m.host not in (host, "*"):
                continue
            if not _match_path(m.path, path):
                continue
            if m.headers and not _match_headers(m.headers, headers):
                continue
            logger.debug(f"gRPC route matched: {route.id} for {path}")
            return route
        logger.debug(f"No gRPC route matched for {path}")
        return None

    def resolve_upstream(self, route: RouteConfig, ctx: GatewayContext) -> UpstreamInfo | None:
        """
        Select an upstream target using the route's load-balance strategy.
        Supports: round_robin, random, ip_hash.
        """
        targets = route.upstream.targets
        if not targets:
            return None

        strategy = route.upstream.load_balance

        if strategy == "random":
            import random

            target = random.choices(targets, weights=[t.weight for t in targets], k=1)[0]
        elif strategy == "ip_hash":
            hash_key = ctx.upstream_hash_key or ctx.rate_limit_key or ctx.request_id
            idx = hash(hash_key) % len(targets)
            target = targets[idx]
        else:
            idx = self._round_robin_counters[route.id] % len(targets)
            self._round_robin_counters[route.id] += 1
            target = targets[idx]

        return UpstreamInfo(
            url=target.url,
            protocol=Protocol[
                route.upstream.type.upper()
                if route.upstream.type.upper() in Protocol.__members__
                else "HTTP"
            ],
            weight=target.weight,
        )
