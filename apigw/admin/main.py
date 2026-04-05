"""
Admin API Gateway entry point.
Run with: uvicorn admin.main:app --host 0.0.0.0 --port 9000
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from admin.app import create_admin_app
from gateway.config import ConfigLoader, settings
from gateway.core.redis import close_redis, init_redis
from gateway.core.router import RoutingEngine
from gateway.observability.logging import configure_logging

# Configure logging
configure_logging(level=settings.observability.log_level, fmt=settings.observability.log_format)

_config_loader = ConfigLoader(settings.routes_config, settings.gateway_config)
_routing_engine = RoutingEngine()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    await init_redis()
    await _config_loader.load()
    _routing_engine.update_routes(_config_loader.routes)
    yield
    await close_redis()

app = create_admin_app(routing_engine=_routing_engine, config_loader=_config_loader)
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
