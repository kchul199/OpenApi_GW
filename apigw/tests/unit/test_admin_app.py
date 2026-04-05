"""
Unit tests for the admin control-plane app.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import yaml  # type: ignore[import-untyped]

from admin.app import create_admin_app
from gateway.config.loader import GatewayConfig, PluginConfig, RouteConfig
from gateway.config.settings import settings
from gateway.core.router import RoutingEngine

from .conftest import make_route


class _ConfigLoaderStub:
    def __init__(self) -> None:
        self.routes = [
            make_route(
                id="users-http",
                protocol="HTTP",
                path="/api/users/**",
                plugins=[PluginConfig(name="jwt-validator"), PluginConfig(name="request-logger")],
            ),
            make_route(
                id="chat-ws",
                protocol="WebSocket",
                path="/ws/chat",
                upstream_type="WebSocket",
            ),
        ]
        self.gateway = GatewayConfig(
            name="Test Gateway",
            version="9.9.9",
            global_plugins=[PluginConfig(name="request-logger")],
        )
        self.reload_calls = 0

    async def reload(self) -> None:
        self.reload_calls += 1

    def validate_route_payload(self, payload: dict[str, object]) -> RouteConfig:
        return RouteConfig.model_validate(payload)

    def render_routes_yaml(self, routes: list[RouteConfig]) -> str:
        return yaml.safe_dump(
            {"routes": [route.model_dump(mode="python", exclude_none=True) for route in routes]},
            sort_keys=False,
            allow_unicode=True,
        )

    async def create_route(self, route: RouteConfig) -> None:
        if any(existing.id == route.id for existing in self.routes):
            raise ValueError(f"Route '{route.id}' already exists")
        self.routes.append(route)

    async def update_route(self, current_route_id: str, route: RouteConfig) -> None:
        for index, existing in enumerate(self.routes):
            if existing.id == current_route_id:
                if route.id != current_route_id and any(
                    candidate.id == route.id for candidate in self.routes
                ):
                    raise ValueError(f"Route '{route.id}' already exists")
                self.routes[index] = route
                return
        raise KeyError(current_route_id)

    async def delete_route(self, route_id: str) -> None:
        before_count = len(self.routes)
        self.routes = [route for route in self.routes if route.id != route_id]
        if len(self.routes) == before_count:
            raise KeyError(route_id)


def _build_client() -> tuple[TestClient, _ConfigLoaderStub]:
    loader = _ConfigLoaderStub()
    temp_root = Path("/tmp") / f"apigw-admin-test-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    app = create_admin_app(
        RoutingEngine(),
        loader,  # type: ignore[arg-type]
        key_store_file=str(temp_root / "admin_keys.json"),
        audit_log_file=str(temp_root / "admin_audit.log"),
        route_history_file=str(temp_root / "route_history.json"),
    )
    return TestClient(app), loader


def test_admin_ui_serves_html() -> None:
    client, _ = _build_client()

    response = client.get("/ui")

    assert response.status_code == 200
    assert "API 관리 화면" in response.text


def test_dashboard_requires_admin_key() -> None:
    client, _ = _build_client()

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 401


def test_dashboard_returns_summary() -> None:
    client, _ = _build_client()

    response = client.get(
        "/api/v1/dashboard",
        headers={"X-Admin-Key": settings.admin.api_key},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["gateway"]["name"] == "Test Gateway"
    assert payload["summary"]["route_count"] == 2
    assert payload["protocols"]["HTTP"] == 1
    assert payload["protocols"]["WEBSOCKET"] == 1


def test_reload_endpoint_refreshes_config() -> None:
    client, loader = _build_client()

    response = client.post(
        "/api/v1/reload",
        headers={"X-Admin-Key": settings.admin.api_key},
    )

    assert response.status_code == 200
    assert loader.reload_calls == 1


def test_validate_route_returns_normalized_payload() -> None:
    client, _ = _build_client()
    route = make_route(id="preview-route").model_dump(mode="python", exclude_none=True)

    response = client.post(
        "/api/v1/routes/validate",
        headers={"X-Admin-Key": settings.admin.api_key},
        json=route,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["normalized_route"]["id"] == "preview-route"


def test_preview_route_returns_diff() -> None:
    client, _ = _build_client()
    route_obj = make_route(id="users-http")
    route_obj.description = "Edited"
    route = route_obj.model_dump(mode="python", exclude_none=True)

    response = client.post(
        "/api/v1/routes/preview?current_route_id=users-http",
        headers={"X-Admin-Key": settings.admin.api_key},
        json=route,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "update"
    assert "Edited" in payload["diff"]


def test_create_route_endpoint_persists_new_route() -> None:
    client, loader = _build_client()
    route = make_route(id="new-admin-route").model_dump(mode="python", exclude_none=True)

    response = client.post(
        "/api/v1/routes",
        headers={"X-Admin-Key": settings.admin.api_key},
        json=route,
    )

    assert response.status_code == 201
    assert any(item.id == "new-admin-route" for item in loader.routes)


def test_update_route_endpoint_supports_rename() -> None:
    client, loader = _build_client()
    route = make_route(id="users-http-v2", path="/api/users/v2/**").model_dump(
        mode="python",
        exclude_none=True,
    )

    response = client.put(
        "/api/v1/routes/users-http",
        headers={"X-Admin-Key": settings.admin.api_key},
        json=route,
    )

    assert response.status_code == 200
    assert any(item.id == "users-http-v2" for item in loader.routes)
    assert not any(item.id == "users-http" for item in loader.routes)


def test_delete_route_endpoint_removes_route() -> None:
    client, loader = _build_client()

    response = client.delete(
        "/api/v1/routes/chat-ws",
        headers={"X-Admin-Key": settings.admin.api_key},
    )

    assert response.status_code == 200
    assert not any(item.id == "chat-ws" for item in loader.routes)


def test_read_key_cannot_write() -> None:
    client, _ = _build_client()

    rotate_response = client.post(
        "/api/v1/admin/keys/rotate",
        headers={"X-Admin-Key": settings.admin.api_key},
        json={"role": "read", "label": "read-only"},
    )
    read_key = rotate_response.json()["new_key"]["secret"]
    route = make_route(id="read-forbidden").model_dump(mode="python", exclude_none=True)

    response = client.post(
        "/api/v1/routes",
        headers={"X-Admin-Key": read_key},
        json=route,
    )

    assert response.status_code == 403


def test_history_and_rollback_flow() -> None:
    client, loader = _build_client()
    route = make_route(id="rollback-target").model_dump(mode="python", exclude_none=True)
    create_response = client.post(
        "/api/v1/routes",
        headers={"X-Admin-Key": settings.admin.api_key},
        json=route,
    )
    assert create_response.status_code == 201

    update_route = make_route(id="rollback-target", path="/api/rollback/v2/**").model_dump(
        mode="python",
        exclude_none=True,
    )
    update_response = client.put(
        "/api/v1/routes/rollback-target",
        headers={"X-Admin-Key": settings.admin.api_key},
        json=update_route,
    )
    assert update_response.status_code == 200

    history_response = client.get(
        "/api/v1/routes/history?limit=10",
        headers={"X-Admin-Key": settings.admin.api_key},
    )
    assert history_response.status_code == 200
    entries = history_response.json()["entries"]
    update_entry = next(entry for entry in entries if entry["action"] == "update")

    rollback_response = client.post(
        f"/api/v1/routes/history/{update_entry['id']}/rollback",
        headers={"X-Admin-Key": settings.admin.api_key},
    )
    assert rollback_response.status_code == 200
    assert any(route_item.id == "rollback-target" for route_item in loader.routes)
    restored = next(route_item for route_item in loader.routes if route_item.id == "rollback-target")
    assert restored.match.path == "/api/**"
