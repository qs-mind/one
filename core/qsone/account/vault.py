"""The account's key vault (decision 13, built by O1 in the auth repo): `GET`, `PUT` and
`DELETE <issuer>/api/vault/{name}`, with an access token that has the scope `vault`. It holds one
opaque value of at most 4 KB per account and name.

One keeps exactly one value there: the Backup key, under "one-backup-key", as
`{"v": 1, "key_id", "key"}` (the key in base64). Never a project key: a Confidential Project's
key is never wrapped by the Backup key, and no other key goes to the vault.
"""

import base64
import binascii
import json
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from qsone import settings
from qsone.account import oidc
from qsone.backup import keys

if TYPE_CHECKING:
    from qsone.account.session import Account

log = logging.getLogger(__name__)

NAME = "one-backup-key"
KEEP_SECONDS = 5 * 60  # a value read from the vault is trusted this long (the Backup screen asks)
OFFLINE_SECONDS = 60  # after an offline call, the next call fails at once for this long


class VaultError(Exception):
    """The vault could not be read or written: signed out, offline, refused, or a value that
    does not hold up. Callers of an escrow log the class and go on without it."""


def encode(backup_key: bytes) -> str:
    return json.dumps(
        {"v": 1, "key_id": keys.key_id(backup_key), "key": base64.b64encode(backup_key).decode()}
    )


def decode(value: object) -> bytes:
    """Raises `VaultError` for a value that is not a Backup key One wrote."""
    try:
        doc = json.loads(value) if isinstance(value, str) else None
        key = base64.b64decode(doc["key"], validate=True) if isinstance(doc, dict) else b""
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise VaultError("the vault value cannot be read") from None
    if doc.get("v") != 1 or len(key) != 32 or doc.get("key_id") != keys.key_id(key):
        raise VaultError("the vault value is not a Backup key")
    return key


class AccountEscrow:
    """`backup.keys.Escrow` with the account's vault. `get()` is None only when the vault has no
    Backup key; every failure raises, so a caller never takes "offline" for "nothing there"."""

    def __init__(self, account: "Account") -> None:
        self.account = account
        self._lock = threading.Lock()
        self._known: tuple[bytes | None, float] | None = None  # (value, monotonic time read)
        self._offline_at: float | None = None

    def get(self) -> bytes | None:
        with self._lock:
            if self._known is not None and time.monotonic() - self._known[1] < KEEP_SECONDS:
                return self._known[0]
        answer = self._call("GET")
        if answer.status_code == 404:
            found = None
        else:
            try:
                found = decode(answer.json().get("value"))
            except (ValueError, AttributeError):
                raise VaultError("the vault answer cannot be read") from None
        with self._lock:
            self._known = (found, time.monotonic())
        return found

    def put(self, backup_key: bytes) -> None:
        self._call("PUT", json={"value": encode(backup_key)})
        with self._lock:
            self._known = (backup_key, time.monotonic())
        log.info("The Backup key is in the account vault")

    def _call(self, method: str, **kwargs) -> httpx.Response:
        with self._lock:
            if (
                self._offline_at is not None
                and time.monotonic() - self._offline_at < OFFLINE_SECONDS
            ):
                raise VaultError("offline")
        client = self.account.client()
        url = f"{client.issuer}/api/vault/{NAME}"
        for again in (True, False):
            token = self.account.access_token()
            if token is None:
                raise VaultError("signed out or offline")
            try:
                answer = client.request(
                    method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
                )
            except oidc.Failed as e:
                if e.offline:
                    with self._lock:
                        self._offline_at = time.monotonic()
                raise VaultError(type(e).__name__) from None
            with self._lock:
                self._offline_at = None
            if answer.status_code == 401 and again:
                self.account.drop_access()  # refused elsewhere, or ended early: refresh once
                continue
            if answer.is_success or (method == "GET" and answer.status_code == 404):
                return answer
            raise VaultError(f"the vault answered {answer.status_code}")
        raise VaultError("the vault refused the access token")


def backup_folder() -> Path | None:
    """The backup folder the engineer picked (the Backups runner's `backup.folder`)."""
    saved = settings.load().get("backup")
    folder = saved.get("folder") if isinstance(saved, dict) else None
    return Path(folder) if isinstance(folder, str) and folder else None


def settle_backup_key(escrow: AccountEscrow | None, data_dir: Path) -> None:
    """After a sign-in, in one step: if the vault holds a Backup key, it wins, and every local
    and backed-up key.json is wrapped again with it (`adopt_backup_key`); otherwise this
    computer's Backup key (made now if there is none) goes to the vault. Raises `VaultError`
    and `KeyringError`; the session tries again after its next refresh."""
    if escrow is None:
        return
    held = escrow.get()
    local = keys.backup_key()
    if held is None:
        escrow.put(local if local is not None else keys.ensure_backup_key())
    elif held != local:
        count = keys.adopt_backup_key(held, data_dir, backup_folder())
        log.info("The account's Backup key adopted: %d key files wrapped again", count)
