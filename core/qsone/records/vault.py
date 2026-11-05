"""Project keys live only in the system key store: one random 32-byte key per project, as hex,
under service "QS Mind One", user "project:<id>". Never log or return a key."""

import secrets

import keyring

from qsone.keys import SERVICE


def _user(project_id: str) -> str:
    return f"project:{project_id}"


def create_key(project_id: str) -> bytes:
    """Raises `keyring.errors.KeyringError` when the system key store is not available."""
    key = secrets.token_bytes(32)
    keyring.set_password(SERVICE, _user(project_id), key.hex())
    return key


def get_key(project_id: str) -> bytes | None:
    """Raises `keyring.errors.KeyringError` when the system key store is not available."""
    value = keyring.get_password(SERVICE, _user(project_id))
    return bytes.fromhex(value) if value else None


def delete_key(project_id: str) -> None:
    """Only to undo a failed create."""
    keyring.delete_password(SERVICE, _user(project_id))


def put_key(project_id: str, key: bytes) -> None:
    """Puts a project key back (from its key.json or a backup). Raises `KeyringError`."""
    keyring.set_password(SERVICE, _user(project_id), key.hex())
