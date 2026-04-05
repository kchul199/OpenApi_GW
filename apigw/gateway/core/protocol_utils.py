"""
Helpers shared across HTTP-like protocol adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import re

from fastapi import Request, Response
import grpc
from starlette.requests import Request as StarletteRequest

from gateway.config.loader import RouteConfig
from gateway.core.context import GatewayContext

_PEER_RE = re.compile(r"^(?P<proto>ipv4|ipv6):(?P<host>.+):(?P<port>\d+)$")

_HTTP_TO_GRPC_STATUS = {
    400: grpc.StatusCode.INVALID_ARGUMENT,
    401: grpc.StatusCode.UNAUTHENTICATED,
    403: grpc.StatusCode.PERMISSION_DENIED,
    404: grpc.StatusCode.NOT_FOUND,
    408: grpc.StatusCode.DEADLINE_EXCEEDED,
    409: grpc.StatusCode.ABORTED,
    429: grpc.StatusCode.RESOURCE_EXHAUSTED,
    499: grpc.StatusCode.CANCELLED,
    500: grpc.StatusCode.INTERNAL,
    501: grpc.StatusCode.UNIMPLEMENTED,
    502: grpc.StatusCode.UNAVAILABLE,
    503: grpc.StatusCode.UNAVAILABLE,
    504: grpc.StatusCode.DEADLINE_EXCEEDED,
}

_HTTP_TO_WS_CLOSE = {
    400: 4400,
    401: 4401,
    403: 4403,
    404: 4404,
    408: 4408,
    409: 4409,
    429: 4429,
    500: 4500,
    502: 4502,
    503: 4503,
    504: 4504,
}


async def _empty_receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


def build_synthetic_request(
    *,
    path: str,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    query_string: str | bytes = b"",
    client: tuple[str, int] | None = None,
    scheme: str = "http",
) -> Request:
    query_bytes = query_string.encode() if isinstance(query_string, str) else query_string
    header_items = [
        (str(key).lower().encode("latin-1"), str(value).encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": method.upper(),
        "path": path,
        "query_string": query_bytes,
        "headers": header_items,
        "server": ("gateway", 0),
        "client": client or ("127.0.0.1", 0),
        "root_path": "",
        "scheme": scheme,
    }
    return StarletteRequest(scope, _empty_receive)


def client_from_peer(peer: str | None) -> tuple[str, int]:
    if not peer:
        return ("127.0.0.1", 0)
    match = _PEER_RE.match(peer)
    if not match:
        return ("127.0.0.1", 0)
    host = match.group("host").strip("[]")
    return (host, int(match.group("port")))


def first_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def build_upstream_hash_key(request: Request, route: RouteConfig, ctx: GatewayContext) -> str:
    strategy = route.upstream.hash_on.lower()
    key_name = route.upstream.hash_key

    if strategy == "client_ip":
        return first_client_ip(request)
    if strategy == "request_id":
        return ctx.request_id
    if strategy == "path":
        return request.url.path
    if strategy == "header" and key_name:
        return request.headers.get(key_name, ctx.request_id)
    if strategy == "query_param" and key_name:
        return request.query_params.get(key_name, ctx.request_id)
    return ctx.request_id


def http_status_to_grpc_status(status_code: int) -> grpc.StatusCode:
    return _HTTP_TO_GRPC_STATUS.get(status_code, grpc.StatusCode.UNKNOWN)


def http_status_to_websocket_close(status_code: int) -> int:
    return _HTTP_TO_WS_CLOSE.get(status_code, 1011)


def response_detail(response: Response, fallback: str) -> str:
    body = getattr(response, "body", b"") or b""
    if not body:
        return fallback
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return fallback
    detail = payload.get("detail")
    return detail if isinstance(detail, str) and detail else fallback
