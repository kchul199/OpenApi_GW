"""
Generic gRPC proxy handler with configurable RPC cardinality.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Sequence
import logging
from pathlib import Path
from typing import Any, cast

from fastapi import Request, Response
import grpc

from gateway.config.loader import GatewayConfig, GRPCProxyConfig, RouteConfig
from gateway.core.context import GatewayContext, UpstreamInfo
from gateway.core.pipeline import MiddlewarePipeline
from gateway.core.protocol_utils import (
    build_synthetic_request,
    build_upstream_hash_key,
    client_from_peer,
    http_status_to_grpc_status,
    response_detail,
)
from gateway.core.router import RoutingEngine

logger = logging.getLogger(__name__)

PreparedCall = tuple[GatewayContext, UpstreamInfo, Sequence[tuple[str, str]]]


def _identity(value: bytes) -> bytes:
    return value


class GenericGRPCProxy(grpc.GenericRpcHandler):  # type: ignore[misc]
    """
    Catches incoming gRPC calls and proxies them to configured upstreams.

    Because the gateway doesn't compile descriptors, the route config must
    declare the RPC cardinality (`unary_unary`, `unary_stream`,
    `stream_unary`, `stream_stream`) for each proxied gRPC route.
    """

    def __init__(
        self,
        router: RoutingEngine,
        gateway_config_provider: Callable[[], GatewayConfig],
    ) -> None:
        self._router = router
        self._gateway_config_provider = gateway_config_provider
        self._channels: dict[tuple[str, bool, str | None], grpc.aio.Channel] = {}

    def service(
        self, handler_call_details: grpc.HandlerCallDetails
    ) -> grpc.RpcMethodHandler | None:
        method = handler_call_details.method
        headers = {key.lower(): value for key, value in handler_call_details.invocation_metadata}
        host = headers.get("host", headers.get(":authority", ""))
        route = self._router.match_grpc(path=method, host=host, headers=headers)

        if not route:
            logger.warning("No gRPC route found", extra={"method": method})
            return grpc.unary_unary_rpc_method_handler(
                self._not_found_handler,
                request_deserializer=_identity,
                response_serializer=_identity,
            )

        return self._build_method_handler(route, method)

    async def close(self) -> None:
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()

    def _build_method_handler(self, route: RouteConfig, method: str) -> grpc.RpcMethodHandler:
        cardinality = route.grpc.cardinality

        if cardinality == "stream_stream":
            return grpc.stream_stream_rpc_method_handler(
                self._stream_stream(route, method),
                request_deserializer=_identity,
                response_serializer=_identity,
            )
        if cardinality == "stream_unary":
            return grpc.stream_unary_rpc_method_handler(
                self._stream_unary(route, method),
                request_deserializer=_identity,
                response_serializer=_identity,
            )
        if cardinality == "unary_stream":
            return grpc.unary_stream_rpc_method_handler(
                self._unary_stream(route, method),
                request_deserializer=_identity,
                response_serializer=_identity,
            )
        return grpc.unary_unary_rpc_method_handler(
            self._unary_unary(route, method),
            request_deserializer=_identity,
            response_serializer=_identity,
        )

    async def _not_found_handler(self, request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        del request
        await context.abort(grpc.StatusCode.NOT_FOUND, "Route not found")
        raise RuntimeError("unreachable")

    def _unary_unary(
        self,
        route: RouteConfig,
        method: str,
    ) -> Callable[[bytes, grpc.aio.ServicerContext], Any]:
        async def handler(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
            prepared = await self._prepare_call(route, method, context)
            if prepared is None:
                return b""
            ctx, target, metadata = prepared
            call = self._channel_for(target.url, route.grpc).unary_unary(
                method,
                request_serializer=_identity,
                response_deserializer=_identity,
            )(
                request,
                metadata=metadata,
                timeout=route.grpc.timeout or route.upstream.timeout,
                wait_for_ready=route.grpc.wait_for_ready,
            )
            try:
                initial_metadata = await call.initial_metadata()
                if initial_metadata:
                    await context.send_initial_metadata(initial_metadata)
                response = cast(bytes, await call)
                trailing_metadata = await call.trailing_metadata()
                if trailing_metadata:
                    context.set_trailing_metadata(trailing_metadata)
                return response
            except grpc.aio.AioRpcError as exc:
                logger.error(
                    "gRPC unary-unary proxy error",
                    extra={"route_id": ctx.route_id, "code": exc.code().name},
                )
                await context.abort(exc.code(), exc.details())
                raise RuntimeError("unreachable") from None

        return handler

    def _unary_stream(
        self,
        route: RouteConfig,
        method: str,
    ) -> Callable[[bytes, grpc.aio.ServicerContext], Any]:
        async def handler(
            request: bytes, context: grpc.aio.ServicerContext
        ) -> AsyncIterator[bytes]:
            prepared = await self._prepare_call(route, method, context)
            if prepared is None:
                return
            ctx, target, metadata = prepared
            call = self._channel_for(target.url, route.grpc).unary_stream(
                method,
                request_serializer=_identity,
                response_deserializer=_identity,
            )(
                request,
                metadata=metadata,
                timeout=route.grpc.timeout or route.upstream.timeout,
                wait_for_ready=route.grpc.wait_for_ready,
            )
            try:
                initial_metadata = await call.initial_metadata()
                if initial_metadata:
                    await context.send_initial_metadata(initial_metadata)
                async for response in call:
                    yield response
                trailing_metadata = await call.trailing_metadata()
                if trailing_metadata:
                    context.set_trailing_metadata(trailing_metadata)
            except grpc.aio.AioRpcError as exc:
                logger.error(
                    "gRPC unary-stream proxy error",
                    extra={"route_id": ctx.route_id, "code": exc.code().name},
                )
                await context.abort(exc.code(), exc.details())
                return

        return handler

    def _stream_unary(
        self,
        route: RouteConfig,
        method: str,
    ) -> Callable[[AsyncIterator[bytes], grpc.aio.ServicerContext], Any]:
        async def handler(
            request_iterator: AsyncIterator[bytes],
            context: grpc.aio.ServicerContext,
        ) -> bytes:
            prepared = await self._prepare_call(route, method, context)
            if prepared is None:
                return b""
            ctx, target, metadata = prepared
            call = self._channel_for(target.url, route.grpc).stream_unary(
                method,
                request_serializer=_identity,
                response_deserializer=_identity,
            )(
                request_iterator,
                metadata=metadata,
                timeout=route.grpc.timeout or route.upstream.timeout,
                wait_for_ready=route.grpc.wait_for_ready,
            )
            try:
                initial_metadata = await call.initial_metadata()
                if initial_metadata:
                    await context.send_initial_metadata(initial_metadata)
                response = cast(bytes, await call)
                trailing_metadata = await call.trailing_metadata()
                if trailing_metadata:
                    context.set_trailing_metadata(trailing_metadata)
                return response
            except grpc.aio.AioRpcError as exc:
                logger.error(
                    "gRPC stream-unary proxy error",
                    extra={"route_id": ctx.route_id, "code": exc.code().name},
                )
                await context.abort(exc.code(), exc.details())
                raise RuntimeError("unreachable") from None

        return handler

    def _stream_stream(
        self,
        route: RouteConfig,
        method: str,
    ) -> Callable[[AsyncIterator[bytes], grpc.aio.ServicerContext], Any]:
        async def handler(
            request_iterator: AsyncIterator[bytes],
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator[bytes]:
            prepared = await self._prepare_call(route, method, context)
            if prepared is None:
                return
            ctx, target, metadata = prepared
            call = self._channel_for(target.url, route.grpc).stream_stream(
                method,
                request_serializer=_identity,
                response_deserializer=_identity,
            )(
                request_iterator,
                metadata=metadata,
                timeout=route.grpc.timeout or route.upstream.timeout,
                wait_for_ready=route.grpc.wait_for_ready,
            )
            try:
                initial_metadata = await call.initial_metadata()
                if initial_metadata:
                    await context.send_initial_metadata(initial_metadata)
                async for response in call:
                    yield response
                trailing_metadata = await call.trailing_metadata()
                if trailing_metadata:
                    context.set_trailing_metadata(trailing_metadata)
            except grpc.aio.AioRpcError as exc:
                logger.error(
                    "gRPC stream-stream proxy error",
                    extra={"route_id": ctx.route_id, "code": exc.code().name},
                )
                await context.abort(exc.code(), exc.details())
                return

        return handler

    async def _prepare_call(
        self,
        route: RouteConfig,
        method: str,
        context: grpc.aio.ServicerContext,
    ) -> PreparedCall | None:
        ctx = GatewayContext()
        ctx.route_id = route.id

        metadata: dict[str, str] = {
            key.lower(): value for key, value in context.invocation_metadata()
        }
        synthetic_request = build_synthetic_request(
            path=method,
            method="POST",
            headers=metadata,
            client=client_from_peer(context.peer()),
        )
        ctx.upstream_hash_key = build_upstream_hash_key(synthetic_request, route, ctx)
        response = await self._run_preflight(route, synthetic_request, ctx)
        if response is not None and response.status_code >= 400:
            await context.abort(
                http_status_to_grpc_status(response.status_code),
                response_detail(response, "gRPC request rejected by gateway"),
            )
            return None

        target = self._router.resolve_upstream(route, ctx)
        if not target:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "No upstream servers available")
            return None

        return ctx, target, self._forward_metadata(context.invocation_metadata(), ctx, route.grpc)

    async def _run_preflight(
        self,
        route: RouteConfig,
        request: Request,
        ctx: GatewayContext,
    ) -> Response:
        pipeline = MiddlewarePipeline(self._gateway_config_provider().global_plugins)

        async def allow_handler(_request: Request, _ctx: GatewayContext) -> Response:
            return Response(status_code=204)

        return await pipeline.execute(request, ctx, route.plugins, allow_handler)

    def _forward_metadata(
        self,
        metadata: Iterable[tuple[str, str]],
        ctx: GatewayContext,
        grpc_config: GRPCProxyConfig,
    ) -> Sequence[tuple[str, str]]:
        dropped = {key.lower() for key in grpc_config.drop_metadata}
        forwarded = [(key, value) for key, value in metadata if key.lower() not in dropped]
        if grpc_config.inject_request_id and not any(
            key.lower() == "x-request-id" for key, _ in forwarded
        ):
            forwarded.append(("x-request-id", ctx.request_id))
        return forwarded

    def _channel_for(self, target_url: str, grpc_config: GRPCProxyConfig) -> grpc.aio.Channel:
        normalized_target = (
            target_url.replace("grpc://", "")
            .replace("grpcs://", "")
            .replace("http://", "")
            .replace("https://", "")
        )
        secure = grpc_config.secure
        if secure is None:
            secure = target_url.startswith(("grpcs://", "https://"))

        cache_key = (normalized_target, secure, grpc_config.root_cert_file)
        channel = self._channels.get(cache_key)
        if channel is not None:
            return channel

        if secure:
            root_certificates = None
            if grpc_config.root_cert_file:
                root_certificates = Path(grpc_config.root_cert_file).read_bytes()
            credentials = grpc.ssl_channel_credentials(root_certificates=root_certificates)
            channel = grpc.aio.secure_channel(normalized_target, credentials)
        else:
            channel = grpc.aio.insecure_channel(normalized_target)

        self._channels[cache_key] = cast(grpc.aio.Channel, channel)
        return cast(grpc.aio.Channel, channel)
