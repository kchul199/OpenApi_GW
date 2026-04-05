"""
Unit tests for gateway/core/proxy.py

Covers:
  - _filter_headers: hop-by-hop headers removed, safe headers preserved
  - HTTPReverseProxy._build_url: simple path, strip_prefix, query string
  - HTTPReverseProxy.proxy: success (200), timeout (504), connect error (502),
                             not initialized (503), no upstream resolved (502)
"""

from __future__ import annotations

import httpx
import pytest

from gateway.core.context import GatewayContext, Protocol, UpstreamInfo
from gateway.core.proxy import HOP_BY_HOP_HEADERS, HTTPReverseProxy, _filter_headers

from .conftest import make_request, make_route

# ── _filter_headers ───────────────────────────────────────────────────────────


class TestFilterHeaders:
    def test_removes_all_hop_by_hop_headers(self):
        headers = dict.fromkeys(HOP_BY_HOP_HEADERS, "value")
        result = _filter_headers(headers)
        assert result == {}

    def test_preserves_safe_headers(self):
        headers = {
            "content-type": "application/json",
            "x-custom-header": "val",
            "authorization": "Bearer token",
            "transfer-encoding": "chunked",  # hop-by-hop → removed
        }
        result = _filter_headers(headers)
        assert "content-type" in result
        assert "x-custom-header" in result
        assert "authorization" in result
        assert "transfer-encoding" not in result

    def test_empty_headers(self):
        assert _filter_headers({}) == {}

    def test_case_sensitive_hop_by_hop_removal(self):
        # HOP_BY_HOP_HEADERS are lowercase; input must match lowercase
        headers = {"connection": "keep-alive", "x-safe": "yes"}
        result = _filter_headers(headers)
        assert "connection" not in result
        assert "x-safe" in result


# ── HTTPReverseProxy._build_url ───────────────────────────────────────────────


class TestBuildUrl:
    def _proxy(self) -> HTTPReverseProxy:
        return HTTPReverseProxy()

    def test_simple_path_forwarding(self):
        proxy = self._proxy()
        route = make_route(path="/api/**", strip_prefix=False)
        req = make_request(path="/api/v1/users")
        url = proxy._build_url("http://backend:8000", req, route)
        assert url == "http://backend:8000/api/v1/users"

    def test_strip_prefix_removes_path_prefix(self):
        proxy = self._proxy()
        route = make_route(path="/api/**", strip_prefix=True)
        req = make_request(path="/api/v1/users")
        url = proxy._build_url("http://backend:8000", req, route)
        assert url == "http://backend:8000/v1/users"

    def test_strip_prefix_root_becomes_slash(self):
        proxy = self._proxy()
        route = make_route(path="/api/**", strip_prefix=True)
        req = make_request(path="/api")
        url = proxy._build_url("http://backend:8000", req, route)
        assert url == "http://backend:8000/"

    def test_query_string_appended(self):
        proxy = self._proxy()
        route = make_route(path="/api/**", strip_prefix=False)
        req = make_request(path="/api/search", query_string=b"q=hello&page=2")
        url = proxy._build_url("http://backend:8000", req, route)
        assert url == "http://backend:8000/api/search?q=hello&page=2"

    def test_trailing_slash_in_base_trimmed(self):
        proxy = self._proxy()
        route = make_route(path="/api/**", strip_prefix=False)
        req = make_request(path="/api/items")
        url = proxy._build_url("http://backend:8000/", req, route)
        assert url == "http://backend:8000/api/items"


# ── HTTPReverseProxy.proxy ────────────────────────────────────────────────────


class TestHTTPReverseProxy:
    @pytest.fixture
    async def proxy(self):
        p = HTTPReverseProxy(timeout=5.0)
        await p.startup()
        yield p
        await p.shutdown()

    def _ctx(self, upstream_url: str = "http://backend:8000") -> GatewayContext:
        ctx = GatewayContext()
        ctx.route_id = "test-route"
        ctx.upstream = UpstreamInfo(url=upstream_url, protocol=Protocol.HTTP)
        return ctx

    async def test_successful_proxy(self, proxy, httpx_mock):
        httpx_mock.add_response(
            url="http://backend:8000/api/test",
            status_code=200,
            content=b'{"result":"ok"}',
            headers={"content-type": "application/json"},
        )
        route = make_route(upstream_url="http://backend:8000")
        req = make_request(path="/api/test")
        resp = await proxy.proxy(req, self._ctx(), route)
        assert resp.status_code == 200
        assert b"ok" in resp.body

    async def test_request_id_forwarded_in_response(self, proxy, httpx_mock):
        httpx_mock.add_response(url="http://backend:8000/api/test", status_code=200, content=b"")
        route = make_route(upstream_url="http://backend:8000")
        ctx = self._ctx()
        req = make_request(path="/api/test")
        resp = await proxy.proxy(req, ctx, route)
        assert resp.headers.get("x-request-id") == ctx.request_id

    async def test_upstream_timeout_returns_504(self, proxy, httpx_mock):
        httpx_mock.add_exception(httpx.TimeoutException("timeout"))
        route = make_route(upstream_url="http://backend:8000", retry_count=0)
        req = make_request(path="/api/test")
        resp = await proxy.proxy(req, self._ctx(), route)
        assert resp.status_code == 504
        assert b"timeout" in resp.body.lower()

    async def test_upstream_connect_error_returns_502(self, proxy, httpx_mock):
        httpx_mock.add_exception(httpx.ConnectError("connection refused"))
        route = make_route(upstream_url="http://backend:8000", retry_count=0)
        req = make_request(path="/api/test")
        resp = await proxy.proxy(req, self._ctx(), route)
        assert resp.status_code == 502

    async def test_no_upstream_returns_502(self, proxy):
        route = make_route(upstream_url="http://backend:8000")
        ctx = GatewayContext()
        ctx.upstream = None  # upstream not resolved
        req = make_request(path="/api/test")
        resp = await proxy.proxy(req, ctx, route)
        assert resp.status_code == 502

    async def test_proxy_not_initialized_returns_503(self):
        proxy = HTTPReverseProxy()
        # Do NOT call startup() → client is None
        route = make_route(upstream_url="http://backend:8000")
        req = make_request(path="/api/test")
        resp = await proxy.proxy(req, self._ctx(), route)
        assert resp.status_code == 503

    async def test_hop_by_hop_headers_not_forwarded(self, proxy, httpx_mock):
        """Hop-by-hop headers from the client must not reach the upstream.

        Uses 'te' (TE: trailers) as the test hop-by-hop header because
        httpx adds its own 'connection: keep-alive' automatically, making
        'connection' unsuitable for asserting filter behaviour.
        """
        httpx_mock.add_response(url="http://backend:8000/api/test", status_code=200, content=b"")
        route = make_route(upstream_url="http://backend:8000")
        req = make_request(
            path="/api/test",
            headers={
                "te": "trailers",  # hop-by-hop → must be stripped
                "x-custom": "val",  # application header → must be forwarded
            },
        )
        await proxy.proxy(req, self._ctx(), route)

        sent = httpx_mock.get_requests()[0]
        sent_headers = {k.lower(): v for k, v in sent.headers.items()}
        assert "te" not in sent_headers
        assert "x-custom" in sent_headers

    async def test_retry_on_502_status(self, proxy, httpx_mock):
        """Upstream 502 should be retried according to retry config."""
        httpx_mock.add_response(url="http://backend:8000/api/test", status_code=502)
        httpx_mock.add_response(url="http://backend:8000/api/test", status_code=200, content=b"ok")
        route = make_route(upstream_url="http://backend:8000", retry_count=1)
        req = make_request(path="/api/test")
        resp = await proxy.proxy(req, self._ctx(), route)
        assert resp.status_code == 200
