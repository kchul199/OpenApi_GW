"""
Gateway configuration system using Pydantic Settings.
Supports loading from environment variables and .env files.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080
    grpc_port: int = 9090
    workers: int = 1
    reload: bool = False
    access_log: bool = True
    # TLS
    tls_enabled: bool = False
    tls_cert_file: str = ""
    tls_key_file: str = ""


class RedisSettings(BaseSettings):
    url: str = "redis://localhost:6379/0"
    cluster_mode: bool = False
    max_connections: int = 100
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 2.0


class ObservabilitySettings(BaseSettings):
    # Tracing
    tracing_enabled: bool = True
    otel_exporter_endpoint: str = "http://localhost:4317"
    service_name: str = "open-api-gateway"
    # Metrics
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json | text


class AdminSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 9000
    api_key: str = Field(default="changeme-admin-key", description="Admin API 접근 키")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    app_name: str = "Open API Gateway"
    environment: str = "development"  # development | staging | production
    debug: bool = False

    # Routes config file path
    routes_config: str = "config/routes.yaml"
    gateway_config: str = "config/gateway.yaml"

    server: ServerSettings = Field(default_factory=ServerSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    admin: AdminSettings = Field(default_factory=AdminSettings)


# Singleton
settings = Settings()
