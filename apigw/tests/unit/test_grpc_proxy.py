"""
Unit tests for gRPC proxy handler selection and channel creation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from gateway.adapters.grpc_proxy import GenericGRPCProxy
from gateway.config.loader import GatewayConfig
from gateway.core.router import RoutingEngine

from .conftest import make_route


def _gateway_config() -> GatewayConfig:
    return GatewayConfig()


class TestGenericGrpcProxy:
    def test_service_returns_handler_matching_route_cardinality(self):
        engine = RoutingEngine()
        engine.update_routes(
            [
                make_route(
                    id="grpc-route",
                    protocol="gRPC",
                    path="/svc.Greeter/SayHello",
                    upstream_type="gRPC",
                    grpc_cardinality="stream_stream",
                )
            ]
        )
        proxy = GenericGRPCProxy(engine, _gateway_config)
        details = MagicMock(method="/svc.Greeter/SayHello", invocation_metadata=[])
        handler = proxy.service(details)
        assert handler is not None
        assert handler.request_streaming is True
        assert handler.response_streaming is True

    def test_missing_route_returns_unary_unary_not_found_handler(self):
        proxy = GenericGRPCProxy(RoutingEngine(), _gateway_config)
        details = MagicMock(method="/svc.Greeter/SayHello", invocation_metadata=[])
        handler = proxy.service(details)
        assert handler is not None
        assert handler.request_streaming is False
        assert handler.response_streaming is False

    def test_secure_channel_uses_ssl_credentials(self):
        proxy = GenericGRPCProxy(RoutingEngine(), _gateway_config)
        with patch("gateway.adapters.grpc_proxy.grpc.ssl_channel_credentials", return_value="creds") as creds:
            with patch("gateway.adapters.grpc_proxy.grpc.aio.secure_channel", return_value="channel") as channel:
                result = proxy._channel_for(
                    "grpcs://grpc.example.com:443",
                    make_route(protocol="gRPC", upstream_type="gRPC").grpc,
                )
        assert result == "channel"
        creds.assert_called_once()
        channel.assert_called_once()
