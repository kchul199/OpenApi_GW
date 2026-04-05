"""
Admin action audit logger.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


class AdminAuditLogger:
    """Writes admin events as JSON lines."""

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)

    def log(self, event: dict[str, Any]) -> None:
        line_payload = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            **event,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line_payload, ensure_ascii=True, sort_keys=False))
            handle.write("\n")
