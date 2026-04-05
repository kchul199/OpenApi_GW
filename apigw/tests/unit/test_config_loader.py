"""
Unit tests for config loader environment expansion.
"""

from __future__ import annotations

import pytest

from gateway.config.loader import ConfigLoader


def _write_gateway(path, name: str = "Gateway") -> None:
    path.write_text(
        f"""
name: "{name}"
version: "1.0.0"
global_plugins: []
""".strip()
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_loader_expands_env_placeholders(tmp_path, monkeypatch) -> None:
    routes_path = tmp_path / "routes.yaml"
    gateway_path = tmp_path / "gateway.yaml"
    routes_path.write_text(
        """
routes:
  - id: env-route
    match:
      protocol: HTTP
      path: /api/env/**
      methods: [GET]
    upstream:
      type: REST
      targets:
        - url: http://example:8000
          weight: 100
    plugins:
      - name: jwt-validator
        enabled: true
        config:
          secret_key: ${OAG_TEST_JWT_SECRET}
          algorithm: HS256
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _write_gateway(gateway_path, name="${OAG_GATEWAY_NAME:-Open API Gateway}")

    monkeypatch.setenv("OAG_TEST_JWT_SECRET", "unit-test-secret")
    monkeypatch.setenv("OAG_GATEWAY_NAME", "Env Gateway")

    loader = ConfigLoader(str(routes_path), str(gateway_path))
    await loader.load()

    assert loader.gateway.name == "Env Gateway"
    assert loader.routes[0].plugins[0].config["secret_key"] == "unit-test-secret"


@pytest.mark.asyncio
async def test_loader_uses_default_value_when_env_missing(tmp_path) -> None:
    routes_path = tmp_path / "routes.yaml"
    gateway_path = tmp_path / "gateway.yaml"
    routes_path.write_text(
        """
routes:
  - id: fallback-route
    match:
      protocol: HTTP
      path: /api/fallback/**
      methods: [GET]
    upstream:
      type: REST
      targets:
        - url: ${OAG_TARGET_URL:-http://fallback:8000}
          weight: 100
    plugins: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _write_gateway(gateway_path)

    loader = ConfigLoader(str(routes_path), str(gateway_path))
    await loader.load()

    assert loader.routes[0].upstream.targets[0].url == "http://fallback:8000"


@pytest.mark.asyncio
async def test_loader_raises_when_required_env_is_missing(tmp_path) -> None:
    routes_path = tmp_path / "routes.yaml"
    gateway_path = tmp_path / "gateway.yaml"
    routes_path.write_text(
        """
routes:
  - id: missing-env-route
    match:
      protocol: HTTP
      path: /api/missing/**
      methods: [GET]
    upstream:
      type: REST
      targets:
        - url: ${OAG_MISSING_TARGET}
          weight: 100
    plugins: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _write_gateway(gateway_path)

    loader = ConfigLoader(str(routes_path), str(gateway_path))
    with pytest.raises(ValueError, match="OAG_MISSING_TARGET"):
        await loader.load()
