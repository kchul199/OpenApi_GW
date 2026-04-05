"""
Unit tests for admin key store behaviors.
"""

from __future__ import annotations

from admin.security import AdminKeyStore


def _new_store(tmp_path) -> AdminKeyStore:
    return AdminKeyStore(
        file_path=str(tmp_path / "admin_keys.json"),
        bootstrap_write_keys=["bootstrap-write-key"],
        bootstrap_read_keys=[],
    )


def test_create_key_with_ttl_exposes_expiry(tmp_path) -> None:
    store = _new_store(tmp_path)
    created = store.create_key(role="read", label="ttl-read", expires_in_seconds=300)

    assert created["expires_at"]
    assert store.authenticate(created["secret"]) is not None
    listed = next(item for item in store.list_keys() if item["id"] == created["id"])
    assert listed["expired"] is False


def test_expired_key_is_not_authenticated(tmp_path) -> None:
    store = _new_store(tmp_path)
    created = store.create_key(role="write", label="soon-expired", expires_in_seconds=300)

    for record in store._keys:
        if str(record.get("id")) == created["id"]:
            record["expires_at"] = "2000-01-01T00:00:00+00:00"
            break

    assert store.authenticate(created["secret"]) is None
    listed = next(item for item in store.list_keys() if item["id"] == created["id"])
    assert listed["expired"] is True
