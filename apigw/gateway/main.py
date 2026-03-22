"""
Gateway entry point.
Run with: uvicorn gateway.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import logging

import uvicorn

from gateway.app import create_app
from gateway.config import settings
from gateway.observability.logging import configure_logging

configure_logging(level=settings.observability.log_level, fmt=settings.observability.log_format)
logger = logging.getLogger(__name__)

app = create_app()


def main() -> None:
    logger.info(f"Starting {settings.app_name} on {settings.server.host}:{settings.server.port}")
    uvicorn.run(
        "gateway.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        workers=settings.server.workers,
        log_config=None,      # we manage logging ourselves
        access_log=False,     # handled by LoggingPlugin
        http="h11",
        ws="websockets",
    )


if __name__ == "__main__":
    main()
