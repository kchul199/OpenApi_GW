"""
Admin API - control-plane app for managing routes, auth keys, and history.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable
from difflib import unified_diff
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from admin.audit import AdminAuditLogger
from admin.history import RouteHistoryStore
from admin.security import AdminKeyStore, AdminPrincipal, AdminRole
from gateway.config import ConfigLoader, settings
from gateway.config.loader import RouteConfig
from gateway.core.router import RoutingEngine
from gateway.observability.metrics import ADMIN_ACTIONS_TOTAL, ADMIN_AUTH_FAILURES_TOTAL

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=True)
_STATIC_DIR = Path(__file__).with_name("static")


class RotateKeyRequest(BaseModel):
    role: AdminRole = "write"
    label: str = ""
    deactivate_key_id: str | None = None


AuthDependency = Callable[[Request, str], Awaitable[AdminPrincipal]]


def _parse_csv_keys(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]


def _summarize_route(route: RouteConfig) -> dict[str, Any]:
    enabled_plugins = [plugin.name for plugin in route.plugins if plugin.enabled]
    return {
        "id": route.id,
        "description": route.description,
        "protocol": route.match.protocol.upper(),
        "path": route.match.path,
        "methods": route.match.methods,
        "host": route.match.host,
        "match_headers": route.match.headers,
        "upstream_type": route.upstream.type.upper(),
        "targets": [target.url for target in route.upstream.targets],
        "target_count": len(route.upstream.targets),
        "load_balance": route.upstream.load_balance,
        "hash_on": route.upstream.hash_on,
        "hash_key": route.upstream.hash_key,
        "timeout": route.upstream.timeout,
        "plugins": enabled_plugins,
        "plugin_count": len(enabled_plugins),
        "strip_prefix": route.strip_prefix,
        "preserve_host": route.preserve_host,
    }


def _route_to_yaml(config_loader: ConfigLoader, route: RouteConfig) -> str:
    return config_loader.render_routes_yaml([route]).rstrip()


def _build_dashboard_payload(config_loader: ConfigLoader) -> dict[str, Any]:
    routes = config_loader.routes
    protocol_counts = Counter(route.match.protocol.upper() for route in routes)
    upstream_type_counts = Counter(route.upstream.type.upper() for route in routes)
    plugin_usage = Counter(
        plugin.name
        for route in routes
        for plugin in route.plugins
        if plugin.enabled
    )
    global_plugins = [
        plugin.name for plugin in config_loader.gateway.global_plugins if plugin.enabled
    ]
    routes_without_plugins = [route.id for route in routes if not any(p.enabled for p in route.plugins)]

    return {
        "gateway": {
            "name": config_loader.gateway.name,
            "version": config_loader.gateway.version,
            "environment": settings.environment,
        },
        "summary": {
            "route_count": len(routes),
            "upstream_count": sum(len(route.upstream.targets) for route in routes),
            "global_plugin_count": len(global_plugins),
            "configured_plugin_count": len(plugin_usage),
        },
        "protocols": dict(sorted(protocol_counts.items())),
        "upstream_types": dict(sorted(upstream_type_counts.items())),
        "global_plugins": global_plugins,
        "plugin_usage": [
            {"name": name, "count": count} for name, count in plugin_usage.most_common()
        ],
        "insights": {
            "routes_without_plugins": routes_without_plugins,
            "sticky_routes": sum(1 for route in routes if route.upstream.load_balance == "ip_hash"),
            "grpc_routes": protocol_counts.get("GRPC", 0),
            "websocket_routes": protocol_counts.get("WEBSOCKET", 0),
        },
        "routes": [_summarize_route(route) for route in routes],
    }


def _build_route_preview(
    config_loader: ConfigLoader,
    route: RouteConfig,
    current_route_id: str | None = None,
) -> dict[str, Any]:
    existing = next(
        (
            candidate
            for candidate in config_loader.routes
            if candidate.id == (current_route_id or route.id)
        ),
        None,
    )
    next_route_yaml = _route_to_yaml(config_loader, route)
    previous_route_yaml = _route_to_yaml(config_loader, existing) if existing is not None else ""
    diff_lines = list(
        unified_diff(
            previous_route_yaml.splitlines(),
            next_route_yaml.splitlines(),
            fromfile=f"{current_route_id or 'new'} (before)",
            tofile=f"{route.id} (after)",
            lineterm="",
        )
    )
    return {
        "mode": "update" if existing is not None else "create",
        "normalized_route": route.model_dump(mode="python", exclude_none=True),
        "diff": "\n".join(diff_lines) if diff_lines else "No changes",
    }


def _find_route(config_loader: ConfigLoader, route_id: str) -> RouteConfig | None:
    for route in config_loader.routes:
        if route.id == route_id:
            return route
    return None


async def _publish_reload_event() -> None:
    try:
        from gateway.core.redis import get_redis

        publish = getattr(get_redis(), "publish", None)
        if callable(publish):
            await cast(Any, publish)("oag:config_reload", "reload")
    except Exception:
        pass


def create_admin_app(
    routing_engine: RoutingEngine,
    config_loader: ConfigLoader,
    *,
    key_store_file: str | None = None,
    audit_log_file: str | None = None,
    route_history_file: str | None = None,
) -> FastAPI:
    bootstrap_write_keys = [settings.admin.api_key, *_parse_csv_keys(settings.admin.write_api_keys)]
    bootstrap_read_keys = _parse_csv_keys(settings.admin.read_api_keys)
    key_store = AdminKeyStore(
        key_store_file or settings.admin.key_store_file,
        bootstrap_write_keys=bootstrap_write_keys,
        bootstrap_read_keys=bootstrap_read_keys,
    )
    audit_logger = AdminAuditLogger(audit_log_file or settings.admin.audit_log_file)
    history_store = RouteHistoryStore(
        route_history_file or settings.admin.route_history_file,
        max_entries=settings.admin.route_history_max_entries,
    )

    def _audit(
        request: Request,
        principal: AdminPrincipal | None,
        action: str,
        status: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        audit_logger.log(
            {
                "action": action,
                "status": status,
                "actor_key_id": principal.key_id if principal else "",
                "actor_role": principal.role if principal else "",
                "ip": request.client.host if request.client else "",
                "path": request.url.path,
                "detail": detail or {},
            }
        )

    def _require_role(required_role: AdminRole) -> AuthDependency:
        async def _dependency(
            request: Request,
            key: str = Security(_api_key_header),
        ) -> AdminPrincipal:
            principal = key_store.authenticate(key)
            if principal is None:
                ADMIN_AUTH_FAILURES_TOTAL.labels(required_role=required_role, reason="invalid").inc()
                _audit(request, None, action="auth", status="invalid_key")
                raise HTTPException(status_code=401, detail="Invalid Admin API Key")
            if not key_store.is_allowed(principal, required_role):
                ADMIN_AUTH_FAILURES_TOTAL.labels(required_role=required_role, reason="forbidden").inc()
                _audit(
                    request,
                    principal,
                    action="auth",
                    status="forbidden",
                    detail={"required_role": required_role},
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"'{required_role}' role required",
                )
            return principal

        return _dependency

    require_read = _require_role("read")
    require_write = _require_role("write")

    admin = FastAPI(
        title="OAG Admin API",
        version="1.1.0",
        description="Open API Gateway - Admin Control Plane",
    )

    admin.mount("/ui/static", StaticFiles(directory=str(_STATIC_DIR)), name="admin-ui-static")

    @admin.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/ui")

    @admin.get("/ui", include_in_schema=False)
    async def admin_ui() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @admin.get("/api/v1/dashboard", tags=["dashboard"])
    async def dashboard(_principal: AdminPrincipal = Security(require_read)) -> dict[str, Any]:
        return _build_dashboard_payload(config_loader)

    @admin.get("/api/v1/routes", tags=["routes"])
    async def list_routes(_principal: AdminPrincipal = Security(require_read)) -> dict[str, Any]:
        return {"routes": [r.model_dump() for r in config_loader.routes]}

    @admin.post("/api/v1/routes/validate", tags=["routes"])
    async def validate_route(
        payload: dict[str, Any],
        _principal: AdminPrincipal = Security(require_read),
    ) -> dict[str, Any]:
        try:
            route = config_loader.validate_route_payload(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "status": "valid",
            "normalized_route": route.model_dump(mode="python", exclude_none=True),
        }

    @admin.post("/api/v1/routes/preview", tags=["routes"])
    async def preview_route(
        payload: dict[str, Any],
        current_route_id: str | None = None,
        _principal: AdminPrincipal = Security(require_read),
    ) -> dict[str, Any]:
        try:
            route = config_loader.validate_route_payload(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _build_route_preview(config_loader, route, current_route_id=current_route_id)

    @admin.get("/api/v1/routes/history", tags=["routes"])
    async def list_route_history(
        limit: int = 30,
        _principal: AdminPrincipal = Security(require_read),
    ) -> dict[str, Any]:
        return {"entries": history_store.list_entries(limit=limit)}

    @admin.get("/api/v1/routes/{route_id}", tags=["routes"])
    async def get_route(
        route_id: str,
        _principal: AdminPrincipal = Security(require_read),
    ) -> dict[str, Any]:
        route = _find_route(config_loader, route_id)
        if route is None:
            raise HTTPException(status_code=404, detail=f"Route '{route_id}' not found")
        return route.model_dump()

    @admin.post("/api/v1/routes", tags=["routes"], status_code=201)
    async def create_route(
        request: Request,
        payload: dict[str, Any],
        principal: AdminPrincipal = Security(require_write),
    ) -> dict[str, Any]:
        try:
            route = config_loader.validate_route_payload(payload)
            await config_loader.create_route(route)
        except ValueError as exc:
            ADMIN_ACTIONS_TOTAL.labels(action="route_create", status="conflict").inc()
            _audit(request, principal, "route_create", "conflict", {"reason": str(exc)})
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValidationError as exc:
            ADMIN_ACTIONS_TOTAL.labels(action="route_create", status="invalid").inc()
            _audit(request, principal, "route_create", "invalid", {"reason": str(exc)})
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        route_dump = route.model_dump(mode="python", exclude_none=True)
        history_store.append(
            action="create",
            route_id=route.id,
            actor_key_id=principal.key_id,
            actor_role=principal.role,
            before=None,
            after=route_dump,
            note="route-created",
        )
        routing_engine.update_routes(config_loader.routes)
        await _publish_reload_event()
        ADMIN_ACTIONS_TOTAL.labels(action="route_create", status="ok").inc()
        _audit(request, principal, "route_create", "ok", {"route_id": route.id})
        return {"status": "created", "route": route_dump}

    @admin.put("/api/v1/routes/{route_id}", tags=["routes"])
    async def update_route(
        route_id: str,
        request: Request,
        payload: dict[str, Any],
        principal: AdminPrincipal = Security(require_write),
    ) -> dict[str, Any]:
        before_route = _find_route(config_loader, route_id)
        if before_route is None:
            ADMIN_ACTIONS_TOTAL.labels(action="route_update", status="not_found").inc()
            _audit(request, principal, "route_update", "not_found", {"route_id": route_id})
            raise HTTPException(status_code=404, detail=f"Route '{route_id}' not found")

        try:
            route = config_loader.validate_route_payload(payload)
            await config_loader.update_route(route_id, route)
        except ValueError as exc:
            ADMIN_ACTIONS_TOTAL.labels(action="route_update", status="conflict").inc()
            _audit(request, principal, "route_update", "conflict", {"reason": str(exc)})
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValidationError as exc:
            ADMIN_ACTIONS_TOTAL.labels(action="route_update", status="invalid").inc()
            _audit(request, principal, "route_update", "invalid", {"reason": str(exc)})
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        before_dump = before_route.model_dump(mode="python", exclude_none=True)
        after_dump = route.model_dump(mode="python", exclude_none=True)
        history_store.append(
            action="update",
            route_id=route.id,
            actor_key_id=principal.key_id,
            actor_role=principal.role,
            before=before_dump,
            after=after_dump,
            note=f"updated-from:{route_id}",
        )
        routing_engine.update_routes(config_loader.routes)
        await _publish_reload_event()
        ADMIN_ACTIONS_TOTAL.labels(action="route_update", status="ok").inc()
        _audit(request, principal, "route_update", "ok", {"route_id": route.id})
        return {"status": "updated", "route": after_dump}

    @admin.delete("/api/v1/routes/{route_id}", tags=["routes"])
    async def delete_route(
        route_id: str,
        request: Request,
        principal: AdminPrincipal = Security(require_write),
    ) -> dict[str, Any]:
        route = _find_route(config_loader, route_id)
        if route is None:
            ADMIN_ACTIONS_TOTAL.labels(action="route_delete", status="not_found").inc()
            _audit(request, principal, "route_delete", "not_found", {"route_id": route_id})
            raise HTTPException(status_code=404, detail=f"Route '{route_id}' not found")

        await config_loader.delete_route(route_id)
        before_dump = route.model_dump(mode="python", exclude_none=True)
        history_store.append(
            action="delete",
            route_id=route_id,
            actor_key_id=principal.key_id,
            actor_role=principal.role,
            before=before_dump,
            after=None,
            note="route-deleted",
        )
        routing_engine.update_routes(config_loader.routes)
        await _publish_reload_event()
        ADMIN_ACTIONS_TOTAL.labels(action="route_delete", status="ok").inc()
        _audit(request, principal, "route_delete", "ok", {"route_id": route_id})
        return {"status": "deleted", "route_id": route_id}

    @admin.post("/api/v1/routes/history/{entry_id}/rollback", tags=["routes"])
    async def rollback_route(
        entry_id: str,
        request: Request,
        principal: AdminPrincipal = Security(require_write),
    ) -> dict[str, Any]:
        entry = history_store.find(entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"History entry '{entry_id}' not found")

        before_snapshot = cast(dict[str, Any] | None, entry.get("before"))
        after_snapshot = cast(dict[str, Any] | None, entry.get("after"))
        rollback_before: dict[str, Any] | None = None
        rollback_after: dict[str, Any] | None = None

        if before_snapshot is None and after_snapshot is not None:
            target_id = str(after_snapshot["id"])
            target_route = _find_route(config_loader, target_id)
            if target_route is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot rollback create: route '{target_id}' is already missing",
                )
            rollback_before = target_route.model_dump(mode="python", exclude_none=True)
            await config_loader.delete_route(target_id)
            rollback_after = None
        elif before_snapshot is not None and after_snapshot is None:
            restored_route = config_loader.validate_route_payload(before_snapshot)
            existing_route = _find_route(config_loader, restored_route.id)
            if existing_route is None:
                await config_loader.create_route(restored_route)
            else:
                await config_loader.update_route(restored_route.id, restored_route)
            rollback_before = (
                existing_route.model_dump(mode="python", exclude_none=True)
                if existing_route is not None
                else None
            )
            rollback_after = restored_route.model_dump(mode="python", exclude_none=True)
        elif before_snapshot is not None and after_snapshot is not None:
            restored_route = config_loader.validate_route_payload(before_snapshot)
            current_id = str(after_snapshot["id"])
            existing_current = _find_route(config_loader, current_id)
            if existing_current is not None:
                rollback_before = existing_current.model_dump(mode="python", exclude_none=True)
                await config_loader.update_route(current_id, restored_route)
            else:
                existing_restored = _find_route(config_loader, restored_route.id)
                if existing_restored is None:
                    rollback_before = None
                    await config_loader.create_route(restored_route)
                else:
                    rollback_before = existing_restored.model_dump(mode="python", exclude_none=True)
                    await config_loader.update_route(restored_route.id, restored_route)
            rollback_after = restored_route.model_dump(mode="python", exclude_none=True)
        else:
            raise HTTPException(status_code=422, detail="History entry has no rollback context")

        history_store.append(
            action="rollback",
            route_id=str(entry.get("route_id", "")),
            actor_key_id=principal.key_id,
            actor_role=principal.role,
            before=rollback_before,
            after=rollback_after,
            note=f"rollback-of:{entry_id}",
        )
        routing_engine.update_routes(config_loader.routes)
        await _publish_reload_event()
        ADMIN_ACTIONS_TOTAL.labels(action="route_rollback", status="ok").inc()
        _audit(request, principal, "route_rollback", "ok", {"entry_id": entry_id})
        return {"status": "rolled_back", "history_entry_id": entry_id}

    @admin.post("/api/v1/reload", tags=["config"])
    async def reload_config(
        request: Request,
        principal: AdminPrincipal = Security(require_write),
    ) -> dict[str, Any]:
        await config_loader.reload()
        routing_engine.update_routes(config_loader.routes)
        await _publish_reload_event()
        ADMIN_ACTIONS_TOTAL.labels(action="config_reload", status="ok").inc()
        _audit(request, principal, "config_reload", "ok")
        return {"status": "reloaded", "routes": len(config_loader.routes)}

    @admin.get("/api/v1/plugins", tags=["plugins"])
    async def list_plugins(_principal: AdminPrincipal = Security(require_read)) -> dict[str, Any]:
        from gateway.plugins.base import PluginRegistry

        return {
            "plugins": PluginRegistry.list_plugins(),
            "global_plugins": [
                plugin.name for plugin in config_loader.gateway.global_plugins if plugin.enabled
            ],
        }

    @admin.get("/api/v1/admin/keys", tags=["admin"])
    async def list_admin_keys(principal: AdminPrincipal = Security(require_write)) -> dict[str, Any]:
        ADMIN_ACTIONS_TOTAL.labels(action="key_list", status="ok").inc()
        return {"keys": key_store.list_keys(), "requested_by": principal.key_id}

    @admin.post("/api/v1/admin/keys/rotate", tags=["admin"])
    async def rotate_admin_key(
        payload: RotateKeyRequest,
        request: Request,
        principal: AdminPrincipal = Security(require_write),
    ) -> dict[str, Any]:
        created = key_store.create_key(role=payload.role, label=payload.label)
        deactivated = False
        if payload.deactivate_key_id:
            deactivated = key_store.deactivate_key(payload.deactivate_key_id)
        ADMIN_ACTIONS_TOTAL.labels(action="key_rotate", status="ok").inc()
        _audit(
            request,
            principal,
            "key_rotate",
            "ok",
            {"new_key_id": created["id"], "deactivated": deactivated},
        )
        return {
            "status": "rotated",
            "new_key": created,
            "deactivated": deactivated,
        }

    @admin.post("/api/v1/admin/keys/{key_id}/deactivate", tags=["admin"])
    async def deactivate_admin_key(
        key_id: str,
        request: Request,
        principal: AdminPrincipal = Security(require_write),
    ) -> dict[str, Any]:
        if not key_store.deactivate_key(key_id):
            raise HTTPException(status_code=404, detail=f"Key '{key_id}' not found or inactive")
        ADMIN_ACTIONS_TOTAL.labels(action="key_deactivate", status="ok").inc()
        _audit(request, principal, "key_deactivate", "ok", {"key_id": key_id})
        return {"status": "deactivated", "key_id": key_id}

    @admin.get("/_health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return admin
