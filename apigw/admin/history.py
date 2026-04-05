"""
Route change history storage and rollback helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

HistoryAction = Literal["create", "update", "delete", "rollback"]


class RouteHistoryStore:
    """JSON-based route history with bounded retention."""

    def __init__(self, file_path: str, max_entries: int = 300) -> None:
        self._path = Path(file_path)
        self._max_entries = max_entries
        self._entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._entries = []
            return
        loaded = json.loads(self._path.read_text(encoding="utf-8"))
        self._entries = list(loaded.get("entries", []))

    def _persist(self) -> None:
        payload = {"version": 1, "entries": self._entries[-self._max_entries :]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=False),
            encoding="utf-8",
        )

    def append(
        self,
        *,
        action: HistoryAction,
        route_id: str,
        actor_key_id: str,
        actor_role: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        note: str = "",
    ) -> dict[str, Any]:
        entry = {
            "id": f"hist-{uuid4().hex[:12]}",
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "action": action,
            "route_id": route_id,
            "actor_key_id": actor_key_id,
            "actor_role": actor_role,
            "before": before,
            "after": after,
            "note": note,
        }
        self._entries.append(entry)
        self._persist()
        return entry

    def list_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, self._max_entries))
        return list(reversed(self._entries[-bounded:]))

    def find(self, entry_id: str) -> dict[str, Any] | None:
        for entry in self._entries:
            if str(entry.get("id")) == entry_id:
                return entry
        return None
