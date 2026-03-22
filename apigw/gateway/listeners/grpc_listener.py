"""
gRPC Listener (stub + proxy framework).
Provides a gRPC server that:
  1. Uses gRPC server reflection for discoverability
  2. Proxies calls to upstream gRPC services
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import grpc
from grpc_reflection.v1alpha import reflection

from gateway.adapters.grpc_proxy import GenericGRPCProxy
from gateway.core.router import RoutingEngine

logger = logging.getLogger(__name__)


class GRPCGatewayServer:
    """
    Async gRPC server that acts as a transparent gateway proxy.
    
    For each configured gRPC route, it:
    - Listens for incoming RPC calls
    - Forwards them to upstream gRPC services
    - Returns the upstream response
    """

    def __init__(self, router: RoutingEngine, host: str = "0.0.0.0", port: int = 9090) -> None:
        self._host = host
        self._port = port
        self._router = router
        self._server: grpc.aio.Server | None = None

    async def start(self) -> None:
        self._server = grpc.aio.server(
            options=[
                ("grpc.max_receive_message_length", 64 * 1024 * 1024),   # 64 MB
                ("grpc.max_send_message_length",    64 * 1024 * 1024),
                ("grpc.keepalive_time_ms",          30_000),
                ("grpc.keepalive_timeout_ms",       10_000),
            ]
        )

        # Enable server reflection (grpcurl / tooling discoverability)
        SERVICE_NAMES = (
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(SERVICE_NAMES, self._server)
        
        # Add the generic reverse proxy handler
        self._server.add_generic_rpc_handlers((GenericGRPCProxy(self._router),))

        listen_addr = f"{self._host}:{self._port}"
        self._server.add_insecure_port(listen_addr)

        await self._server.start()
        logger.info(f"gRPC server listening on {listen_addr}")

    async def stop(self, grace: float = 5.0) -> None:
        if self._server:
            await self._server.stop(grace)
            logger.info("gRPC server stopped")

    async def serve(self) -> None:
        """Block until server terminates."""
        if self._server:
            await self._server.wait_for_termination()


async def run_grpc_server(router: RoutingEngine, host: str, port: int) -> None:
    server = GRPCGatewayServer(router, host, port)
    await server.start()
    await server.serve()
