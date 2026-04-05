"""
Prometheus metrics setup using prometheus-fastapi-instrumentator.
"""
from __future__ import annotations

from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

# ── Custom metrics ─────────────────────────────────────────────────────────────

GATEWAY_REQUESTS_TOTAL = Counter(
    "gateway_requests_total",
    "Total number of requests proxied through the gateway",
    labelnames=["route_id", "protocol", "status_code"],
)

GATEWAY_REQUEST_DURATION = Histogram(
    "gateway_request_duration_seconds",
    "Request duration in seconds",
    labelnames=["route_id", "protocol"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

GATEWAY_ACTIVE_CONNECTIONS = Gauge(
    "gateway_active_connections",
    "Number of currently active connections",
    labelnames=["protocol"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "gateway_circuit_breaker_open",
    "1 if circuit breaker is open, 0 if closed",
    labelnames=["route_id"],
)

AUTH_FAILURES_TOTAL = Counter(
    "gateway_auth_failures_total",
    "Total number of authentication failures",
    labelnames=["route_id", "auth_method"],
)

ADMIN_AUTH_FAILURES_TOTAL = Counter(
    "admin_auth_failures_total",
    "Total number of admin authentication/authorization failures",
    labelnames=["required_role", "reason"],
)

ADMIN_ACTIONS_TOTAL = Counter(
    "admin_actions_total",
    "Total number of admin actions",
    labelnames=["action", "status"],
)


def setup_metrics(app: FastAPI, metrics_path: str = "/metrics") -> None:
    """Instrument the FastAPI app with Prometheus metrics."""
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/_health", "/_ready", metrics_path],
    ).instrument(app).expose(app, endpoint=metrics_path, include_in_schema=False)
