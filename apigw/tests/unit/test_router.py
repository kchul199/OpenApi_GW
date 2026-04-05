"""
Unit tests for gateway/core/router.py

Covers:
  - _match_path: exact, prefix (glob), regex, no-match
  - _match_headers: all match, missing key, wrong value
  - RoutingEngine.match: HTTP route selection (path, method, host, header condition)
  - RoutingEngine.match_grpc: gRPC route matching
  - RoutingEngine.resolve_upstream: round_robin, ip_hash, random, empty targets
"""

from __future__ import annotations

from gateway.core.context import GatewayContext, Protocol
from gateway.core.router import RoutingEngine, _match_headers, _match_path

from .conftest import make_request, make_route

# ── _match_path ───────────────────────────────────────────────────────────────


class TestMatchPath:
    def test_exact_match(self):
        assert _match_path("/api/v1/users", "/api/v1/users") is True

    def test_exact_no_match(self):
        assert _match_path("/api/v1/users", "/api/v1/orders") is False

    def test_prefix_glob_match(self):
        assert _match_path("/api/**", "/api/v1/users") is True

    def test_prefix_glob_root_match(self):
        assert _match_path("/api/**", "/api/") is True

    def test_prefix_glob_no_match(self):
        assert _match_path("/api/**", "/grpc/v1/users") is False

    def test_single_wildcard(self):
        assert _match_path("/api/*/detail", "/api/123/detail") is True

    def test_regex_match(self):
        assert _match_path("~/api/v[0-9]+/.*", "/api/v2/users") is True

    def test_regex_no_match(self):
        assert _match_path("~/api/v[0-9]+/.*", "/api/beta/users") is False

    def test_regex_fullmatch_required(self):
        # fullmatch: pattern must cover entire path
        assert _match_path("~/api", "/api/extra") is False


# ── _match_headers ────────────────────────────────────────────────────────────


class TestMatchHeaders:
    def test_all_required_headers_present(self):
        required = {"x-tenant": "acme", "x-env": "prod"}
        actual = {"x-tenant": "acme", "x-env": "prod", "x-other": "val"}
        assert _match_headers(required, actual) is True

    def test_missing_required_header(self):
        required = {"x-tenant": "acme"}
        actual = {"x-other": "val"}
        assert _match_headers(required, actual) is False

    def test_wrong_header_value(self):
        required = {"x-tenant": "acme"}
        actual = {"x-tenant": "other-tenant"}
        assert _match_headers(required, actual) is False

    def test_empty_required_always_passes(self):
        assert _match_headers({}, {"anything": "goes"}) is True


# ── RoutingEngine.match ───────────────────────────────────────────────────────


class TestRoutingEngineMatch:
    def _engine(self, *routes):
        engine = RoutingEngine()
        engine.update_routes(list(routes))
        return engine

    def test_exact_path_match(self):
        route = make_route(path="/health", methods=["GET"])
        engine = self._engine(route)
        req = make_request(method="GET", path="/health")
        assert engine.match(req) is route

    def test_prefix_path_match(self):
        route = make_route(path="/api/**", methods=["GET"])
        engine = self._engine(route)
        req = make_request(method="GET", path="/api/v1/users")
        assert engine.match(req) is route

    def test_wrong_method_no_match(self):
        route = make_route(path="/api/**", methods=["GET"])
        engine = self._engine(route)
        req = make_request(method="POST", path="/api/v1/users")
        assert engine.match(req) is None

    def test_host_filter_match(self):
        route = make_route(path="/", host="api.example.com")
        engine = self._engine(route)
        req = make_request(path="/", headers={"host": "api.example.com"})
        assert engine.match(req) is route

    def test_host_filter_no_match(self):
        route = make_route(path="/", host="api.example.com")
        engine = self._engine(route)
        req = make_request(path="/", headers={"host": "other.example.com"})
        assert engine.match(req) is None

    def test_header_condition_match(self):
        route = make_route(path="/api/**", match_headers={"x-tenant": "acme"})
        engine = self._engine(route)
        req = make_request(path="/api/v1", headers={"x-tenant": "acme"})
        assert engine.match(req) is route

    def test_header_condition_no_match(self):
        route = make_route(path="/api/**", match_headers={"x-tenant": "acme"})
        engine = self._engine(route)
        req = make_request(path="/api/v1", headers={"x-tenant": "other"})
        assert engine.match(req) is None

    def test_first_route_wins(self):
        route_a = make_route(id="A", path="/api/**")
        route_b = make_route(id="B", path="/api/**")
        engine = self._engine(route_a, route_b)
        req = make_request(path="/api/test")
        assert engine.match(req).id == "A"

    def test_no_routes_returns_none(self):
        engine = RoutingEngine()
        req = make_request(path="/any")
        assert engine.match(req) is None

    def test_protocol_mismatch_skipped(self):
        # gRPC route should not match plain HTTP request
        grpc_route = make_route(id="grpc", protocol="gRPC", path="/helloworld.Greeter/SayHello")
        http_route = make_route(id="http", path="/api/**")
        engine = self._engine(grpc_route, http_route)
        req = make_request(path="/api/test")
        assert engine.match(req).id == "http"

    def test_update_routes_replaces_table(self):
        old_route = make_route(id="old", path="/old/**")
        engine = self._engine(old_route)
        new_route = make_route(id="new", path="/new/**")
        engine.update_routes([new_route])
        assert engine.match(make_request(path="/old/path")) is None
        assert engine.match(make_request(path="/new/path")) is new_route


# ── RoutingEngine.match_grpc ──────────────────────────────────────────────────


class TestMatchGrpc:
    def _engine(self, *routes):
        engine = RoutingEngine()
        engine.update_routes(list(routes))
        return engine

    def test_grpc_path_match(self):
        route = make_route(id="grpc-route", protocol="gRPC", path="/helloworld.Greeter/SayHello")
        engine = self._engine(route)
        result = engine.match_grpc(path="/helloworld.Greeter/SayHello")
        assert result is route

    def test_grpc_no_match(self):
        route = make_route(id="grpc-route", protocol="gRPC", path="/helloworld.Greeter/SayHello")
        engine = self._engine(route)
        result = engine.match_grpc(path="/other.Service/Method")
        assert result is None

    def test_grpc_http_route_not_returned(self):
        http_route = make_route(id="http-route", protocol="HTTP", path="/api/**")
        engine = self._engine(http_route)
        result = engine.match_grpc(path="/api/anything")
        assert result is None

    def test_grpc_host_filter(self):
        route = make_route(
            id="grpc-route", protocol="gRPC", path="/svc/**", host="grpc.example.com"
        )
        engine = self._engine(route)
        assert engine.match_grpc(path="/svc/Method", host="grpc.example.com") is route
        assert engine.match_grpc(path="/svc/Method", host="other.example.com") is None


# ── RoutingEngine.resolve_upstream ────────────────────────────────────────────


class TestResolveUpstream:
    def test_round_robin_returns_upstream(self):
        route = make_route(upstream_url="http://backend:8000", load_balance="round_robin")
        engine = RoutingEngine()
        ctx = GatewayContext()
        ctx.request_id = "req-abc"
        result = engine.resolve_upstream(route, ctx)
        assert result is not None
        assert result.url == "http://backend:8000"

    def test_ip_hash_is_sticky(self):
        route = make_route(
            load_balance="ip_hash",
            upstream_targets=[
                ("http://backend-1:8000", 100),
                ("http://backend-2:8000", 100),
            ],
        )
        engine = RoutingEngine()

        ctx1 = GatewayContext()
        ctx1.rate_limit_key = "10.0.0.1"
        ctx2 = GatewayContext()
        ctx2.rate_limit_key = "10.0.0.1"  # same IP → same backend

        result1 = engine.resolve_upstream(route, ctx1)
        result2 = engine.resolve_upstream(route, ctx2)
        assert result1.url == result2.url

    def test_ip_hash_different_ips_may_differ(self):
        route = make_route(
            load_balance="ip_hash",
            upstream_targets=[
                ("http://backend-1:8000", 100),
                ("http://backend-2:8000", 100),
            ],
        )
        engine = RoutingEngine()
        urls = set()
        for i in range(20):
            ctx = GatewayContext()
            ctx.rate_limit_key = f"10.0.0.{i}"
            urls.add(engine.resolve_upstream(route, ctx).url)
        # Over 20 different IPs, at least 2 distinct backends should be hit
        assert len(urls) > 1

    def test_empty_targets_returns_none(self):
        route = make_route()
        route.upstream.targets = []
        engine = RoutingEngine()
        ctx = GatewayContext()
        assert engine.resolve_upstream(route, ctx) is None

    def test_upstream_protocol_is_set(self):
        route = make_route(upstream_url="http://backend:8000")
        engine = RoutingEngine()
        result = engine.resolve_upstream(route, GatewayContext())
        assert result.protocol == Protocol.HTTP

    def test_round_robin_cycles_targets(self):
        route = make_route(
            load_balance="round_robin",
            upstream_targets=[
                ("http://backend-1:8000", 100),
                ("http://backend-2:8000", 100),
            ],
        )
        engine = RoutingEngine()
        first = engine.resolve_upstream(route, GatewayContext())
        second = engine.resolve_upstream(route, GatewayContext())
        third = engine.resolve_upstream(route, GatewayContext())
        assert first.url == "http://backend-1:8000"
        assert second.url == "http://backend-2:8000"
        assert third.url == "http://backend-1:8000"
