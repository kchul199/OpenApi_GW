"""
Admin API key management with role-based authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import secrets
from typing import Any, Literal
from uuid import uuid4

AdminRole = Literal["read", "write"]
_ROLE_RANK: dict[AdminRole, int] = {"read": 1, "write": 2}


@dataclass(frozen=True)
class AdminPrincipal:
    key_id: str
    role: AdminRole
    label: str


class AdminKeyStore:
    """Persistent API key store with hashed secrets."""

    def __init__(
        self,
        file_path: str,
        bootstrap_write_keys: list[str],
        bootstrap_read_keys: list[str],
    ) -> None:
        self._path = Path(file_path)
        self._keys: list[dict[str, Any]] = []
        self._load_or_bootstrap(bootstrap_write_keys, bootstrap_read_keys)

    @staticmethod
    def _hash_secret(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def _persist(self) -> None:
        payload = {"version": 1, "keys": self._keys}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=False),
            encoding="utf-8",
        )

    def _load_or_bootstrap(
        self,
        bootstrap_write_keys: list[str],
        bootstrap_read_keys: list[str],
    ) -> None:
        if self._path.exists():
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
            self._keys = list(loaded.get("keys", []))
            return

        now = datetime.now(tz=UTC).isoformat()
        bootstrap_records: list[dict[str, Any]] = []
        for index, key in enumerate(bootstrap_write_keys):
            secret = key.strip()
            if not secret:
                continue
            bootstrap_records.append(
                {
                    "id": f"write-bootstrap-{index + 1}",
                    "label": "bootstrap-write",
                    "role": "write",
                    "active": True,
                    "created_at": now,
                    "expires_at": None,
                    "secret_sha256": self._hash_secret(secret),
                }
            )
        for index, key in enumerate(bootstrap_read_keys):
            secret = key.strip()
            if not secret:
                continue
            bootstrap_records.append(
                {
                    "id": f"read-bootstrap-{index + 1}",
                    "label": "bootstrap-read",
                    "role": "read",
                    "active": True,
                    "created_at": now,
                    "expires_at": None,
                    "secret_sha256": self._hash_secret(secret),
                }
            )
        self._keys = bootstrap_records
        self._persist()

    @staticmethod
    def _is_expired(record: dict[str, Any], now: datetime | None = None) -> bool:
        expires_at_raw = record.get("expires_at")
        if not expires_at_raw:
            return False
        try:
            expires_at = datetime.fromisoformat(str(expires_at_raw))
        except ValueError:
            # Corrupted timestamp should fail closed.
            return True
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        current = now or datetime.now(tz=UTC)
        return current >= expires_at

    def authenticate(self, secret: str) -> AdminPrincipal | None:
        digest = self._hash_secret(secret)
        for record in self._keys:
            if not record.get("active", False):
                continue
            if self._is_expired(record):
                continue
            if record.get("secret_sha256") != digest:
                continue
            role = str(record.get("role", "read")).lower()
            if role not in ("read", "write"):
                continue
            return AdminPrincipal(
                key_id=str(record["id"]),
                role=role,  # type: ignore[arg-type]
                label=str(record.get("label", "")),
            )
        return None

    def is_allowed(self, principal: AdminPrincipal, required_role: AdminRole) -> bool:
        return _ROLE_RANK[principal.role] >= _ROLE_RANK[required_role]

    def list_keys(self) -> list[dict[str, Any]]:
        return [
            {
                "id": str(record["id"]),
                "label": str(record.get("label", "")),
                "role": str(record.get("role", "read")),
                "active": bool(record.get("active", False)),
                "created_at": str(record.get("created_at", "")),
                "expires_at": str(record.get("expires_at") or ""),
                "expired": self._is_expired(record),
            }
            for record in self._keys
        ]

    def create_key(
        self,
        role: AdminRole,
        label: str = "",
        expires_in_seconds: int | None = None,
    ) -> dict[str, str]:
        plaintext = secrets.token_urlsafe(32)
        expires_at = None
        if expires_in_seconds is not None and expires_in_seconds > 0:
            expires_at = (datetime.now(tz=UTC) + timedelta(seconds=expires_in_seconds)).isoformat()
        record = {
            "id": f"key-{uuid4().hex[:12]}",
            "label": label.strip() or "rotated-key",
            "role": role,
            "active": True,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "expires_at": expires_at,
            "secret_sha256": self._hash_secret(plaintext),
        }
        self._keys.append(record)
        self._persist()
        return {
            "id": str(record["id"]),
            "role": role,
            "secret": plaintext,
            "expires_at": str(record.get("expires_at") or ""),
        }

    def deactivate_key(self, key_id: str) -> bool:
        changed = False
        for record in self._keys:
            if str(record.get("id")) != key_id:
                continue
            if not record.get("active", False):
                break
            record["active"] = False
            changed = True
            break
        if changed:
            self._persist()
        return changed
