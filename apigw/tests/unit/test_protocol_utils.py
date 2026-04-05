"""
Unit tests for protocol helpers shared by WebSocket and gRPC adapters.
"""

from __future__ import annotations

import grpc

from gateway.core.context import GatewayContext
from gateway.core.protocol_utils import (
    build_synthetic_request,
    build_upstream_hash_key,
    client_from_peer,
    http_status_to_grpc_status,
    http_status_to_websocket_close,
)

from .conftest import make_route


class TestClientFromPeer:
    def test_ipv4_peer_is_parsed(self):
        assert client_from_peer("ipv4:10.0.0.1:50051") == ("10.0.0.1", 50051)

    def test_unknown_peer_falls_back(self):
        assert client_from_peer("unix:/tmp/grpc.sock") == ("127.0.0.1", 0)


class TestBuildUpstreamHashKey:
    def test_client_ip_strategy_uses_forwarded_header(self):
        route = make_route(load_balance="ip_hash", hash_on="client_ip")
        request = build_synthetic_request(
            path="/ws/chat",
            headers={"x-forwarded-for": "203.0.113.5, 10.0.0.2"},
        )
        assert build_upstream_hash_key(request, route, GatewayContext()) == "203.0.113.5"

    def test_header_strategy_is_customizable(self):
        route = make_route(load_balance="ip_hash", hash_on="header", hash_key="x-session-id")
        request = build_synthetic_request(path="/ws/chat", headers={"x-session-id": "session-1"})
        assert build_upstream_hash_key(request, route, GatewayContext()) == "session-1"


class TestStatusMappings:
    def test_http_status_maps_to_grpc(self):
        assert http_status_to_grpc_status(401) == grpc.StatusCode.UNAUTHENTICATED
        assert http_status_to_grpc_status(429) == grpc.StatusCode.RESOURCE_EXHAUSTED

    def test_http_status_maps_to_websocket_close_code(self):
        assert http_status_to_websocket_close(403) == 4403
        assert http_status_to_websocket_close(503) == 4503
