"""
Plugin base interface.
All gateway plugins must extend BasePlugin and implement __call__.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response

from gateway.core.context import GatewayContext

# A "next" function in the pipeline chain
NextFunc = Callable[[Request, GatewayContext], Awaitable[Response]]


class BasePlugin(ABC):
    """
    Base class for all gateway middleware plugins.

    Plugins participate in a chain-of-responsibility pattern:
      - They receive the request + context.
      - May short-circuit (return early) or call `next(request, ctx)`.
      - Can mutate headers, context metadata, etc.
    """

    #: Unique name used to reference this plugin in route config
    name: str = "__undefined__"

    #: Execution order (lower = earlier in the chain)
    order: int = 100

    def configure(self, config: dict[str, Any]) -> None:
        """
        Called once with the plugin's per-route or global config dict.
        Override to apply configuration.
        """
        del config

    @abstractmethod
    async def __call__(
        self,
        request: Request,
        ctx: GatewayContext,
        next: NextFunc,
    ) -> Response:
        """Process request and optionally forward to next plugin."""
        ...


class PluginRegistry:
    """Global registry of available plugin types."""

    _registry: dict[str, type[BasePlugin]] = {}

    @classmethod
    def register(cls, plugin_cls: type[BasePlugin]) -> type[BasePlugin]:
        """Decorator to register a plugin class."""
        cls._registry[plugin_cls.name] = plugin_cls
        return plugin_cls

    @classmethod
    def get(cls, name: str) -> type[BasePlugin] | None:
        return cls._registry.get(name)

    @classmethod
    def list_plugins(cls) -> list[str]:
        return sorted(cls._registry.keys())
