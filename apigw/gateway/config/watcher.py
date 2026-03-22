"""
Config File Watcher.
Uses simple polling to detect file modification and trigger a reload.
Designed to work well with Kubernetes ConfigMap updates.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigFileWatcher:
    def __init__(self, *files: str | Path, check_interval: float = 5.0) -> None:
        self._files: list[Path] = [Path(f) for f in files]
        self._check_interval: float = check_interval
        self._mtimes: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._callback = None

    def on_change(self, callback) -> None:
        """Register an async callback to run when files change."""
        self._callback = callback

    async def start(self) -> None:
        """Start the background polling task."""
        # Initialize mtimes
        for f in self._files:
            try:
                self._mtimes[str(f)] = os.stat(f).st_mtime
            except FileNotFoundError:
                self._mtimes[str(f)] = 0.0

        self._task = asyncio.create_task(self._watch_loop())
        logger.info(f"Config watcher started for {len(self._files)} files")

    async def stop(self) -> None:
        """Stop the watcher."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Config watcher stopped")

    async def _watch_loop(self) -> None:
        """Polls file mtimes in an infinite loop."""
        while True:
            await asyncio.sleep(self._check_interval)
            changed = False
            for f in self._files:
                try:
                    current_mtime = os.stat(f).st_mtime
                    if current_mtime != self._mtimes.get(str(f)):
                        self._mtimes[str(f)] = current_mtime
                        changed = True
                        logger.info(f"Config file changed: {f}")
                except FileNotFoundError:
                    if self._mtimes.get(str(f), 0.0) != 0.0:
                        self._mtimes[str(f)] = 0.0
                        changed = True
                        logger.warning(f"Config file deleted: {f}")

            if changed and self._callback is not None:
                try:
                    await self._callback()
                except Exception as e:
                    logger.error(f"Error executing config callback: {e}")
