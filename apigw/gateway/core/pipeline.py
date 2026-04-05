"""
Middleware pipeline engine — Chain of Responsibility pattern.

The pipeline builds a nested async call chain from a list of plugins:
  plugin[0] → plugin[1] → ... → plugin[n] → handler

Each plugin calls `await next(request, ctx)` to proceed.
"""
from __future__ import annotations

import logging

from fastapi import Request, Response

from gateway.config.loader import PluginConfig
from gateway.core.context import GatewayContext
from gateway.plugins.base import BasePlugin, NextFunc, PluginRegistry

logger = logging.getLogger(__name__)

# The innermost "handler" that just returns a 502 if no proxy plugin handled it
async def _default_handler(request: Request, ctx: GatewayContext) -> Response:
    return Response(
        content='{"detail":"No upstream handler resolved the request"}',
        status_code=502,
        media_type="application/json",
    )


def _build_chain(plugins: list[BasePlugin], endpoint: NextFunc) -> NextFunc:
    """
    Recursively wraps plugins around the endpoint, building the execution chain.
    Returns the outermost callable.
    """
    chain = endpoint
    for plugin in reversed(plugins):
        # Capture plugin in closure
        _plugin = plugin
        _next = chain

        async def step(
            request: Request,
            ctx: GatewayContext,
            p: BasePlugin = _plugin,
            n: NextFunc = _next,
        ) -> Response:
            return await p(request, ctx, n)

        chain = step
    return chain


class MiddlewarePipeline:
    """
    Builds and executes the middleware plugin chain for a single request.

    Usage:
        pipeline = MiddlewarePipeline(global_plugins)
        response = await pipeline.execute(request, ctx, route_plugins, proxy_handler)
    """

    def __init__(self, global_plugin_configs: list[PluginConfig]) -> None:
        self._global_configs = global_plugin_configs

    def _instantiate_plugins(self, configs: list[PluginConfig]) -> list[BasePlugin]:
        plugins: list[BasePlugin] = []
        for cfg in configs:
            if not cfg.enabled:
                continue
            cls = PluginRegistry.get(cfg.name)
            if cls is None:
                logger.warning(f"Plugin '{cfg.name}' not found in registry, skipping")
                continue
            instance = cls()
            instance.configure(cfg.config)
            plugins.append(instance)
        # Sort by order
        return sorted(plugins, key=lambda p: p.order)

    async def execute(
        self,
        request: Request,
        ctx: GatewayContext,
        route_plugin_configs: list[PluginConfig],
        proxy_handler: NextFunc,
    ) -> Response:
        """
        Execute the full plugin chain:
          global plugins → route-specific plugins → proxy_handler
        """
        global_plugins = self._instantiate_plugins(self._global_configs)
        route_plugins = self._instantiate_plugins(route_plugin_configs)
        all_plugins = global_plugins + route_plugins

        chain = _build_chain(all_plugins, proxy_handler)
        return await chain(request, ctx)
