"""
End-to-end style flow test for admin console APIs.
"""

from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import yaml  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _FlowConfigLoaderStub:
    def __init__(self) -> None:
        from gateway.config.loader import GatewayConfig, PluginConfig
        from tests.unit.conftest import make_route

        self.routes = [make_route(id="flow-base")]
        self.gateway = GatewayConfig(
            name="Flow Gateway",
            version="1.0.0",
            global_plugins=[PluginConfig(name="request-logger")],
        )
        self.reload_calls = 0

    async def reload(self) -> None:
        self.reload_calls += 1

    def validate_route_payload(self, payload: dict[str, object]):
        from gateway.config.loader import RouteConfig

        return RouteConfig.model_validate(payload)

    def render_routes_yaml(self, routes: list[object]) -> str:
        return yaml.safe_dump(
            {"routes": [route.model_dump(mode="python", exclude_none=True) for route in routes]},
            sort_keys=False,
            allow_unicode=True,
        )

    async def create_route(self, route) -> None:
        if any(item.id == route.id for item in self.routes):
            raise ValueError("duplicated")
        self.routes.append(route)

    async def update_route(self, current_route_id: str, route) -> None:
        for idx, item in enumerate(self.routes):
            if item.id == current_route_id:
                self.routes[idx] = route
                return
        raise KeyError(current_route_id)

    async def delete_route(self, route_id: str) -> None:
        before = len(self.routes)
        self.routes = [item for item in self.routes if item.id != route_id]
        if len(self.routes) == before:
            raise KeyError(route_id)


def _build_client() -> TestClient:
    from admin.app import create_admin_app
    from gateway.core.router import RoutingEngine

    loader = _FlowConfigLoaderStub()
    temp_root = Path("/tmp") / f"apigw-admin-e2e-{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    app = create_admin_app(
        RoutingEngine(),
        loader,  # type: ignore[arg-type]
        key_store_file=str(temp_root / "admin_keys.json"),
        audit_log_file=str(temp_root / "admin_audit.log"),
        route_history_file=str(temp_root / "route_history.json"),
    )
    return TestClient(app)


def test_admin_console_full_flow() -> None:
    from gateway.config.settings import settings
    from tests.unit.conftest import make_route

    client = _build_client()
    key_header = {"X-Admin-Key": settings.admin.api_key}

    ui_response = client.get("/ui")
    assert ui_response.status_code == 200
    assert "Route Editor" in ui_response.text
    assert "Route Changes" in ui_response.text
    assert "Admin Keys" in ui_response.text

    route_payload = make_route(id="e2e-route").model_dump(mode="python", exclude_none=True)
    create_response = client.post("/api/v1/routes", headers=key_header, json=route_payload)
    assert create_response.status_code == 201

    update_payload = make_route(id="e2e-route", path="/api/e2e/v2/**").model_dump(
        mode="python",
        exclude_none=True,
    )
    update_response = client.put("/api/v1/routes/e2e-route", headers=key_header, json=update_payload)
    assert update_response.status_code == 200

    history_response = client.get("/api/v1/routes/history?limit=10", headers=key_header)
    assert history_response.status_code == 200
    update_entry = next(entry for entry in history_response.json()["entries"] if entry["action"] == "update")

    rollback_response = client.post(
        f"/api/v1/routes/history/{update_entry['id']}/rollback",
        headers=key_header,
    )
    assert rollback_response.status_code == 200

    rotate_response = client.post(
        "/api/v1/admin/keys/rotate",
        headers=key_header,
        json={"role": "read", "label": "e2e-read"},
    )
    assert rotate_response.status_code == 200
    read_key = rotate_response.json()["new_key"]["secret"]

    forbidden_create = client.post(
        "/api/v1/routes",
        headers={"X-Admin-Key": read_key},
        json=make_route(id="e2e-forbidden").model_dump(mode="python", exclude_none=True),
    )
    assert forbidden_create.status_code == 403
