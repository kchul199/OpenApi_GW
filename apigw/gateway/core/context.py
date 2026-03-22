"""
Core types and request context used throughout the gateway.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Protocol(str, Enum):
    HTTP = "HTTP"
    GRPC = "gRPC"
    WEBSOCKET = "WebSocket"
    MQTT = "MQTT"


class AuthMethod(str, Enum):
    NONE = "none"
    JWT = "jwt"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    MTLS = "mtls"


@dataclass
class UpstreamInfo:
    """Resolved upstream target for this request."""
    url: str
    protocol: Protocol
    weight: int = 100


@dataclass
class GatewayContext:
    """
    Per-request mutable context passed through the middleware pipeline.
    Plugins read from and write to this object.
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: float = field(default_factory=time.monotonic)

    # Route resolution
    route_id: str = ""
    upstream: UpstreamInfo | None = None

    # Auth
    auth_method: AuthMethod = AuthMethod.NONE
    principal: str = ""         # user/service identifier
    scopes: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)

    # Rate limiting
    rate_limit_key: str = ""

    # Extra metadata plugins can attach
    metadata: dict[str, Any] = field(default_factory=dict)

    # Circuit breaker state per upstream
    circuit_open: bool = False

    @property
    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.start_time) * 1000
