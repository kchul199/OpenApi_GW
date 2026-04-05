"""
Unit tests for gateway/core/pipeline.py

Covers:
  - _build_chain: plugins execute in sorted order, innermost handler called last
  - MiddlewarePipeline.execute: global + route plugins merged in order
  - Disabled plugins are skipped
  - Unknown plugin names are skipped with a warning
"""
from __future__ import annotations

from fastapi import Response
import pytest

from gateway.config.loader import PluginConfig
from gateway.core.context import GatewayContext
from gateway.core.pipeline import MiddlewarePipeline, _build_chain
from gateway.plugins.base import BasePlugin, PluginRegistry

from .conftest import make_request

# ── Test-only plugins (registered once per session) ───────────────────────────

_EXECUTION_LOG: list[str] = []


class _LogPlugin(BasePlugin):
    """A plugin that appends its tag to _EXECUTION_LOG, then calls next."""
    name = "__log_plugin_base__"
    order = 50

    def configure(self, config: dict) -> None:
        self._tag: str = config.get("tag", "?")

    async def __call__(self, request, ctx, next):
        _EXECUTION_LOG.append(self._tag)
        return await next(request, ctx)


@PluginRegistry.register
class _LogPluginAlpha(_LogPlugin):
    name = "__test_log_alpha__"
    order = 10


@PluginRegistry.register
class _LogPluginBeta(_LogPlugin):
    name = "__test_log_beta__"
    order = 20


@PluginRegistry.register
class _ShortCircuitPlugin(BasePlugin):
    """Always returns 403 without calling next."""
    name = "__test_short_circuit__"
    order = 5

    async def __call__(self, request, ctx, next):
        return Response(content=b'{"detail":"blocked"}', status_code=403)


@pytest.fixture(autouse=True)
def clear_log():
    _EXECUTION_LOG.clear()
    yield
    _EXECUTION_LOG.clear()


# ── _build_chain ──────────────────────────────────────────────────────────────

class TestBuildChain:
    async def test_single_plugin_then_handler(self):
        async def handler(req, ctx):
            _EXECUTION_LOG.append("handler")
            return Response(status_code=200)

        plugin = _LogPluginAlpha()
        plugin.configure({"tag": "alpha"})
        chain = _build_chain([plugin], handler)
        await chain(make_request(), GatewayContext())
        assert _EXECUTION_LOG == ["alpha", "handler"]

    async def test_plugins_execute_in_order(self):
        async def handler(req, ctx):
            _EXECUTION_LOG.append("handler")
            return Response(status_code=200)

        p1 = _LogPluginAlpha()
        p1.configure({"tag": "alpha"})
        p2 = _LogPluginBeta()
        p2.configure({"tag": "beta"})

        chain = _build_chain([p1, p2], handler)
        await chain(make_request(), GatewayContext())
        assert _EXECUTION_LOG == ["alpha", "beta", "handler"]

    async def test_empty_plugin_list_calls_handler(self):
        async def handler(req, ctx):
            _EXECUTION_LOG.append("handler")
            return Response(status_code=200)

        chain = _build_chain([], handler)
        resp = await chain(make_request(), GatewayContext())
        assert resp.status_code == 200
        assert _EXECUTION_LOG == ["handler"]

    async def test_short_circuit_prevents_handler(self):
        async def handler(req, ctx):
            _EXECUTION_LOG.append("handler")
            return Response(status_code=200)

        p = _ShortCircuitPlugin()
        p.configure({})
        chain = _build_chain([p], handler)
        resp = await chain(make_request(), GatewayContext())
        assert resp.status_code == 403
        assert "handler" not in _EXECUTION_LOG


# ── MiddlewarePipeline.execute ────────────────────────────────────────────────

class TestMiddlewarePipeline:
    async def _run(
        self,
        global_configs: list[PluginConfig],
        route_configs: list[PluginConfig],
        handler=None,
    ):
        if handler is None:
            async def handler(req, ctx):
                _EXECUTION_LOG.append("handler")
                return Response(status_code=200)

        pipeline = MiddlewarePipeline(global_plugin_configs=global_configs)
        return await pipeline.execute(
            make_request(), GatewayContext(), route_configs, handler
        )

    async def test_global_plugins_run_before_route_plugins(self):
        global_cfg = [PluginConfig(name="__test_log_alpha__", config={"tag": "global"})]
        route_cfg  = [PluginConfig(name="__test_log_beta__",  config={"tag": "route"})]
        await self._run(global_cfg, route_cfg)
        # alpha (order=10) is global, beta (order=20) is route
        # After merging and sorting by order: alpha → beta → handler
        assert _EXECUTION_LOG == ["global", "route", "handler"]

    async def test_disabled_plugin_is_skipped(self):
        cfg = [PluginConfig(name="__test_log_alpha__", enabled=False, config={"tag": "alpha"})]
        await self._run([], cfg)
        assert "alpha" not in _EXECUTION_LOG
        assert "handler" in _EXECUTION_LOG

    async def test_unknown_plugin_name_is_skipped(self):
        cfg = [PluginConfig(name="__nonexistent_plugin__", config={})]
        resp = await self._run([], cfg)
        # Pipeline should still reach handler (unknown plugin silently skipped)
        assert resp.status_code == 200
        assert "handler" in _EXECUTION_LOG

    async def test_pipeline_returns_proxy_handler_response(self):
        async def proxy_handler(req, ctx):
            return Response(content=b'{"result":"ok"}', status_code=201)

        pipeline = MiddlewarePipeline(global_plugin_configs=[])
        resp = await pipeline.execute(make_request(), GatewayContext(), [], proxy_handler)
        assert resp.status_code == 201

    async def test_short_circuit_plugin_blocks_handler(self):
        route_cfg = [PluginConfig(name="__test_short_circuit__", config={})]
        resp = await self._run([], route_cfg)
        assert resp.status_code == 403
        assert "handler" not in _EXECUTION_LOG
