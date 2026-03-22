"""
Generic gRPC proxy handler for dynamic forwarding.
"""
from __future__ import annotations

import logging
from typing import Any

import grpc

from gateway.config.loader import RouteConfig
from gateway.core.context import GatewayContext, Protocol, UpstreamInfo
from gateway.core.router import RoutingEngine

logger = logging.getLogger(__name__)


class GenericGRPCProxy(grpc.GenericRpcHandler):
    """
    Catches all incoming gRPC calls and proxies them to the upstream.
    """

    def __init__(self, router: RoutingEngine) -> None:
        self.router = router

    def service(self, handler_call_details: grpc.HandlerCallDetails) -> grpc.RpcMethodHandler | None:
        method = handler_call_details.method  # e.g., "/package.Service/Method"
        
        # Determine upstream route
        # For simplicity, we create a fake URI path to match against the Router
        path = method
        headers = dict(handler_call_details.invocation_metadata)
        host = headers.get("host", headers.get(":authority", ""))
        
        route = self.router.match_route(protocol=Protocol.GRPC, host=host, path=path, method="POST", headers=headers)
        
        if not route:
            logger.warning(f"No gRPC route found for {method}")
            return grpc.unary_unary(self._not_found_handler)

        target = self.router.resolve_upstream(route)
        if not target:
            return grpc.unary_unary(self._service_unavailable_handler)
            
        upstream_url = target.url.replace("grpc://", "").replace("http://", "").replace("https://", "")

        return grpc.stream_stream(self._proxy_handler(upstream_url, method))

    async def _not_found_handler(self, request: Any, context: grpc.aio.ServicerContext) -> Any:
        await context.abort(grpc.StatusCode.NOT_FOUND, "Route not found")

    async def _service_unavailable_handler(self, request: Any, context: grpc.aio.ServicerContext) -> Any:
        await context.abort(grpc.StatusCode.UNAVAILABLE, "No upstream servers available")

    def _proxy_handler(self, target_url: str, method: str):
        """
        Returns a generic stream-stream handler that forwards raw bytes.
        """
        async def handler(request_iterator, context: grpc.aio.ServicerContext):
            metadata = context.invocation_metadata()
            # Filter out some pseudo-headers if needed before forwarding
            filtered_metadata = [(k, v) for k, v in metadata if not k.startswith(":")]
            
            try:
                async with grpc.aio.insecure_channel(target_url) as channel:
                    # Dynamically invoke the same method on the upstream
                    call = channel.stream_stream(method)(
                        request_iterator,
                        metadata=filtered_metadata
                    )
                    
                    # Forward initial metadata
                    response_metadata = await call.initial_metadata()
                    if response_metadata:
                        await context.send_initial_metadata(response_metadata)
                    
                    # Forward messages
                    async for response in call:
                        yield response
                    
                    # Forward trailing metadata and status
                    trailing_metadata = await call.trailing_metadata()
                    if trailing_metadata:
                        context.set_trailing_metadata(trailing_metadata)
                        
                    code = await call.code()
                    if code != grpc.StatusCode.OK:
                        details = await call.details()
                        await context.abort(code, details)

            except grpc.aio.AioRpcError as e:
                logger.error(f"gRPC proxy error: {e.code()} - {e.details()}")
                await context.abort(e.code(), e.details())
            except Exception as e:
                logger.error(f"Unexpected gRPC error: {e}")
                await context.abort(grpc.StatusCode.INTERNAL, "Internal Gateway Error")

        return handler
