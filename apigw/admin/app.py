"""
Admin API — FastAPI app for managing routes, plugins, and upstreams at runtime.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from gateway.config import settings
from gateway.core.router import RoutingEngine
from gateway.config.loader import RouteConfig

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=True)


def _verify_admin_key(key: str = Security(_api_key_header)) -> str:
    if key != settings.admin.api_key:
        raise HTTPException(status_code=403, detail="Invalid Admin API Key")
    return key


def create_admin_app(routing_engine: RoutingEngine, config_loader) -> FastAPI:
    admin = FastAPI(
        title="OAG Admin API",
        version="1.0.0",
        description="Open API Gateway — Admin Control Plane",
    )

    # ── Routes Management ─────────────────────────────────────────────────────

    @admin.get("/api/v1/routes", tags=["routes"])
    async def list_routes(_key=Security(_verify_admin_key)):
        return {"routes": [r.model_dump() for r in config_loader.routes]}

    @admin.get("/api/v1/routes/{route_id}", tags=["routes"])
    async def get_route(route_id: str, _key=Security(_verify_admin_key)):
        for r in config_loader.routes:
            if r.id == route_id:
                return r.model_dump()
        raise HTTPException(status_code=404, detail=f"Route '{route_id}' not found")

    @admin.post("/api/v1/reload", tags=["config"])
    async def reload(_key=Security(_verify_admin_key)):
        await config_loader.reload()
        routing_engine.update_routes(config_loader.routes)
        
        # Publish reload event to Redis
        try:
            from gateway.core.redis import get_redis
            await get_redis().publish("oag:config_reload", "reload")
        except Exception:
            pass  # Ignore Redis publish error if Redis is not configured or down

        return {"status": "reloaded", "routes": len(config_loader.routes)}

    # ── Plugins Registry ──────────────────────────────────────────────────────

    @admin.get("/api/v1/plugins", tags=["plugins"])
    async def list_plugins(_key=Security(_verify_admin_key)):
        from gateway.plugins.base import PluginRegistry
        return {"plugins": PluginRegistry.list_plugins()}

    # ── Health ────────────────────────────────────────────────────────────────

    @admin.get("/_health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    return admin
