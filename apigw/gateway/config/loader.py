"""
YAML-based route and gateway configuration loader.
Supports hot-reload via file watch or explicit reload call.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ─── Route Model ──────────────────────────────────────────────────────────────

class MatchConfig(BaseModel):
    protocol: str = "HTTP"          # HTTP | gRPC | WebSocket | MQTT
    host: str | None = None
    path: str = "/"
    methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH"])
    headers: dict[str, str] = Field(default_factory=dict)


class UpstreamTarget(BaseModel):
    url: str
    weight: int = 100


class RetryConfig(BaseModel):
    count: int = 3
    backoff_factor: float = 0.3
    status_codes: list[int] = Field(default_factory=lambda: [502, 503, 504])


class UpstreamConfig(BaseModel):
    type: str = "REST"              # REST | gRPC | WebSocket
    targets: list[UpstreamTarget]
    timeout: float = 30.0           # seconds
    retry: RetryConfig = Field(default_factory=RetryConfig)
    load_balance: str = "round_robin"  # round_robin | random | ip_hash | least_connections


class PluginConfig(BaseModel):
    name: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class RouteConfig(BaseModel):
    id: str
    description: str = ""
    match: MatchConfig
    upstream: UpstreamConfig
    plugins: list[PluginConfig] = Field(default_factory=list)
    strip_prefix: bool = False
    preserve_host: bool = False


# ─── Gateway Config Model ─────────────────────────────────────────────────────

class GatewayConfig(BaseModel):
    name: str = "Open API Gateway"
    version: str = "1.0.0"
    global_plugins: list[PluginConfig] = Field(default_factory=list)


# ─── Loader ───────────────────────────────────────────────────────────────────

class ConfigLoader:
    """Loads and hot-reloads YAML configuration files."""

    def __init__(self, routes_path: str, gateway_path: str) -> None:
        self._routes_path = Path(routes_path)
        self._gateway_path = Path(gateway_path)
        self._routes: list[RouteConfig] = []
        self._gateway_cfg: GatewayConfig = GatewayConfig()
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        """Initial load of all configuration files."""
        async with self._lock:
            self._routes = self._load_routes()
            self._gateway_cfg = self._load_gateway()
        logger.info(
            "Config loaded",
            extra={"routes": len(self._routes), "gateway": self._gateway_cfg.name},
        )

    def _load_routes(self) -> list[RouteConfig]:
        if not self._routes_path.exists():
            logger.warning(f"Routes config not found: {self._routes_path}")
            return []
        raw: dict[str, Any] = yaml.safe_load(self._routes_path.read_text(encoding="utf-8")) or {}
        return [RouteConfig(**r) for r in raw.get("routes", [])]

    def _load_gateway(self) -> GatewayConfig:
        if not self._gateway_path.exists():
            logger.warning(f"Gateway config not found: {self._gateway_path}")
            return GatewayConfig()
        raw: dict[str, Any] = yaml.safe_load(self._gateway_path.read_text(encoding="utf-8")) or {}
        return GatewayConfig(**raw)

    async def reload(self) -> None:
        """Hot-reload configuration without downtime."""
        async with self._lock:
            old_count = len(self._routes)
            self._routes = self._load_routes()
            self._gateway_cfg = self._load_gateway()
        logger.info(
            "Config hot-reloaded",
            extra={"routes_before": old_count, "routes_after": len(self._routes)},
        )

    @property
    def routes(self) -> list[RouteConfig]:
        return self._routes

    @property
    def gateway(self) -> GatewayConfig:
        return self._gateway_cfg
