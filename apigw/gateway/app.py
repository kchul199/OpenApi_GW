"""
FastAPI Application Factory.
Creates and configures the main gateway ASGI application.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import JSONResponse

from gateway.config import ConfigLoader, settings
from gateway.config.watcher import ConfigFileWatcher
from gateway.core.context import GatewayContext, Protocol
from gateway.core.pipeline import MiddlewarePipeline
from gateway.core.proxy import HTTPReverseProxy
from gateway.core.redis import close_redis, init_redis, get_redis
from gateway.core.router import RoutingEngine
from gateway.core.router import RoutingEngine
from gateway.listeners.grpc_listener import GRPCGatewayServer
from gateway.listeners.websocket_listener import WebSocketProxy
from gateway.observability.metrics import setup_metrics
from gateway.observability.tracing import setup_tracing

# ── Import plugins to trigger @PluginRegistry.register ────────────────────────
import gateway.plugins.logging.logging_plugin        # noqa: F401
import gateway.plugins.auth.jwt_plugin               # noqa: F401
import gateway.plugins.auth.apikey_plugin            # noqa: F401
import gateway.plugins.auth.mtls_plugin              # noqa: F401
import gateway.plugins.ratelimit.ratelimit_plugin    # noqa: F401
import gateway.plugins.circuitbreaker.breaker_plugin # noqa: F401

logger = logging.getLogger(__name__)

# ── Shared singletons ─────────────────────────────────────────────────────────
_config_loader  = ConfigLoader(settings.routes_config, settings.gateway_config)
_routing_engine = RoutingEngine()
_http_proxy     = HTTPReverseProxy(timeout=30.0)
_ws_proxy       = WebSocketProxy()
_grpc_server    = GRPCGatewayServer(router=_routing_engine, host="0.0.0.0", port=settings.server.grpc_port)
_config_watcher = ConfigFileWatcher(settings.routes_config, settings.gateway_config)

async def _on_config_changed():
    logger.info("Hot-reloading configuration due to file change...")
    await _config_loader.reload()
    _routing_engine.update_routes(_config_loader.routes)
    logger.info(f"Hot-reload complete. Routes active: {len(_config_loader.routes)}")

_config_watcher.on_change(_on_config_changed)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    # Startup
    await init_redis()
    await _config_loader.load()
    _routing_engine.update_routes(_config_loader.routes)
    await _http_proxy.startup()
    await _grpc_server.start()
    await _config_watcher.start()

    # Redis Pub/Sub for config reload
    import asyncio
    async def _redis_pubsub_listener():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe("oag:config_reload")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    logger.info("Received config_reload from Redis Pub/Sub")
                    await _on_config_changed()
        except asyncio.CancelledError:
            await pubsub.unsubscribe("oag:config_reload")

    pubsub_task = asyncio.create_task(_redis_pubsub_listener())
    
    logger.info(f"{settings.app_name} HTTP started on {settings.server.port}, gRPC on {settings.server.grpc_port} (env={settings.environment})")
    yield
    # Shutdown
    pubsub_task.cancel()
    await _config_watcher.stop()
    await _grpc_server.stop()
    await _http_proxy.shutdown()
    await close_redis()
    logger.info(f"{settings.app_name} shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Open API Gateway — REST, gRPC, WebSocket",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=_lifespan,
    )

    # Setup Observability (Metrics & Tracing)
    setup_metrics(app)
    setup_tracing(app, app_name=settings.app_name)

    # ── Health / Readiness ────────────────────────────────────────────────────
    @app.get("/_health", tags=["system"], include_in_schema=False)
    async def health() -> Response:
        try:
            await get_redis().ping()
            redis_status = "ok"
        except Exception as e:
            logger.error(f"Health check failed (Redis error): {e}")
            return JSONResponse({"status": "error", "reason": "redis_unavailable"}, status_code=503)

        return JSONResponse({"status": "ok", "routes": len(_config_loader.routes), "redis": redis_status})

    @app.get("/_ready", tags=["system"], include_in_schema=False)
    async def readiness() -> dict:
        return {"status": "ready"}

    # ── Hot-reload endpoint ───────────────────────────────────────────────────
    @app.post("/_reload", tags=["system"], include_in_schema=False)
    async def reload_config() -> dict:
        await _config_loader.reload()
        _routing_engine.update_routes(_config_loader.routes)
        return {"status": "reloaded", "routes": len(_config_loader.routes)}

    # ── WebSocket catch-all ───────────────────────────────────────────────────
    @app.websocket("/{path:path}")
    async def websocket_gateway(ws: WebSocket, path: str) -> None:
        ctx = GatewayContext()

        # Fake a Request-like for routing
        class _WSRequest:
            method  = "GET"
            headers = dict(ws.headers)
            client  = ws.client
            url     = ws.url

            class _url:
                path = "/" + path
                query = ""

            url = _url()

        # Build temporary Request for route matching
        from starlette.requests import Request as StarletteRequest
        scope = ws.scope.copy()
        scope["type"] = "http"
        scope["method"] = "GET"
        fake_req = StarletteRequest(scope)

        route = _routing_engine.match(fake_req)
        if route is None or route.upstream.type.upper() != "WEBSOCKET":
            await ws.close(code=4004, reason="No WebSocket route found")
            return

        upstream = _routing_engine.resolve_upstream(route, ctx)
        if not upstream:
            await ws.close(code=4004, reason="No upstream available")
            return

        ctx.route_id = route.id
        ctx.upstream = upstream

        # WebSocket upstream URL (ws:// or wss://)
        upstream_ws_url = upstream.url.replace("http://", "ws://").replace("https://", "wss://")
        await _ws_proxy.proxy(ws, upstream_ws_url, ctx)

    # ── HTTP catch-all (main proxy handler) ───────────────────────────────────
    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    async def http_gateway(request: Request, path: str) -> Response:
        ctx = GatewayContext()

        # Route matching
        route = _routing_engine.match(request)
        if route is None:
            return JSONResponse({"detail": f"No route matched for {request.method} /{path}"}, status_code=404)

        ctx.route_id = route.id
        upstream = _routing_engine.resolve_upstream(route, ctx)
        ctx.upstream = upstream

        # Build pipeline
        cfg = _config_loader.gateway
        pipeline = MiddlewarePipeline(cfg.global_plugins)

        async def proxy_handler(req: Request, c: GatewayContext) -> Response:
            return await _http_proxy.proxy(req, c, route)

        return await pipeline.execute(request, ctx, route.plugins, proxy_handler)

    return app
