"""The Backup key, key wraps and recovery codes. Never log, return or write a key or a code.

- The Backup key: 32 random bytes per engineer, in the key store as "backup-key". Its id is the
  first 16 hex digits of SHA-256("qsone-bk-id" + key). An older Backup key waiting to be
  replaced is kept in the key store as "backup-key:<its id>".
- A wrap (`key.json`): AES-256-GCM with a key from HKDF-SHA256 (Backup key, info "qsone wrap
  v1"), a random 12-byte nonce and the associated data "qsone:<project id>:v1", so a wrap opens
  only for its own project.
- A recovery code: 125 random bits as 25 Crockford base32 characters in five groups. The
  wrapping key comes from scrypt (n = 2^17, r = 8, p = 1, a random 16-byte salt).
"""

import base64
import hashlib
import json
import logging
import os
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import keyring
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from qsone import copy
from qsone.keys import SERVICE
from qsone.records.project import RecordsError

log = logging.getLogger(__name__)

KEY_USER = "backup-key"
KEY_FILE = "key.json"
BACKUP_KEY_FILE = "backup-key.json"  # the Backup key under its recovery code
BACKUP_KEY_WRAP_ID = "backup-key"  # the "project id" in that wrap's associated data
KIND_KEY = "backup_key"  # a wrap by the Backup key
KIND_CODE = "code"  # a wrap by a recovery code

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
_READS_AS = {"O": "0", "I": "1", "L": "1"}
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**17, 8, 1
SCRYPT_MAXMEM = 256 * 1024 * 1024


class BackupError(RecordsError):
    """A refusal the engineer can read; `text` is from `copy`."""


class Escrow(Protocol):
    """Where the Backup key is kept outside this computer (Task 5: the account vault)."""

    def get(self) -> bytes | None: ...
    def put(self, backup_key: bytes) -> None: ...


# The Backup key ---------------------------------------------------------------------------------


def key_id(backup_key: bytes) -> str:
    return hashlib.sha256(b"qsone-bk-id" + backup_key).hexdigest()[:16]


def _read(user: str) -> bytes | None:
    value = keyring.get_password(SERVICE, user)
    return bytes.fromhex(value) if value else None


def backup_key() -> bytes | None:
    """Raises `KeyringError` when the key store is not available."""
    return _read(KEY_USER)


def set_backup_key(new: bytes) -> None:
    keyring.set_password(SERVICE, KEY_USER, new.hex())


def known_key(wanted_id: str) -> bytes | None:
    """The Backup key with this id, if this computer has it: the current one or a kept one."""
    current = backup_key()
    if current is not None and key_id(current) == wanted_id:
        return current
    return _read(f"{KEY_USER}:{wanted_id}")


def keep_key(old: bytes) -> None:
    keyring.set_password(SERVICE, f"{KEY_USER}:{key_id(old)}", old.hex())


def ensure_backup_key(escrow: Escrow | None = None) -> bytes:
    """This computer's Backup key, made the first time it is needed. With an escrow and no local
    key, the escrow's key is taken; a new key is put in the escrow. An escrow that fails (say,
    offline) never stops this: the key stays local. Raises `KeyringError` when the store is down."""
    current = backup_key()
    if current is not None:
        return current
    kept = None
    if escrow is not None:
        try:
            kept = escrow.get()
        except Exception as e:  # noqa: BLE001 - an escrow that fails never blocks a project
            log.warning("The Backup key escrow failed (%s)", type(e).__name__)
            escrow = None
    if kept is not None:
        set_backup_key(kept)
        return kept
    new = secrets.token_bytes(32)
    set_backup_key(new)
    if escrow is not None:
        try:
            escrow.put(new)
        except Exception as e:  # noqa: BLE001
            log.warning("The Backup key escrow failed (%s)", type(e).__name__)
    return new


# Wraps --------------------------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: object) -> bytes:
    if not isinstance(text, str):
        raise ValueError("not base64")
    return base64.b64decode(text, validate=True)


def _aad(project_id: str) -> bytes:
    return f"qsone:{project_id}:v1".encode()


def _from_backup_key(backup_key: bytes) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"qsone wrap v1")
    return hkdf.derive(backup_key)


def _from_code(code: str, salt: bytes) -> bytes:
    return hashlib.scrypt(  # through the module: the tests make it fast
        normalise_code(code).encode("ascii"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=32,
    )


def wrap(key: bytes, *, project_id: str, backup_key: bytes) -> dict:
    nonce = secrets.token_bytes(12)
    data = AESGCM(_from_backup_key(backup_key)).encrypt(nonce, key, _aad(project_id))
    return {
        "v": 1,
        "kind": KIND_KEY,
        "project_id": project_id,
        "key_id": key_id(backup_key),
        "nonce": _b64(nonce),
        "data": _b64(data),
    }


def wrap_with_code(key: bytes, *, project_id: str, code: str) -> dict:
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    data = AESGCM(_from_code(code, salt)).encrypt(nonce, key, _aad(project_id))
    return {
        "v": 1,
        "kind": KIND_CODE,
        "project_id": project_id,
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "data": _b64(data),
    }


def unwrap(doc: dict, *, backup_key: bytes | None = None, code: str | None = None) -> bytes:
    """Raises `BackupError`: BACKUP_KEY_WRONG for a Backup key wrap that this key does not open
    (or that belongs to another project), RECOVERY_CODE_WRONG for a code wrap, BACKUP_NEEDS_CODE
    or BACKUP_NEEDS_SIGN_IN when the needed secret was not given."""
    kind = doc.get("kind")
    if kind == KIND_CODE:
        if not code:
            raise BackupError(copy.BACKUP_NEEDS_CODE)
        wrong = copy.RECOVERY_CODE_WRONG
    elif kind == KIND_KEY:
        if backup_key is None:
            raise BackupError(copy.BACKUP_NEEDS_SIGN_IN)
        wrong = copy.BACKUP_KEY_WRONG
    else:
        raise BackupError(copy.BACKUP_KEY_WRONG)
    try:
        nonce, data = _unb64(doc.get("nonce")), _unb64(doc.get("data"))
        if kind == KIND_CODE:
            assert code is not None
            wrapping = _from_code(code, _unb64(doc.get("salt")))
        else:
            assert backup_key is not None
            wrapping = _from_backup_key(backup_key)
        return AESGCM(wrapping).decrypt(nonce, data, _aad(str(doc.get("project_id"))))
    except (InvalidTag, ValueError):
        raise BackupError(wrong, status=400 if kind == KIND_CODE else 409) from None


# Recovery codes ---------------------------------------------------------------------------------


def new_recovery_code() -> str:
    bits = secrets.randbits(125)
    chars = "".join(ALPHABET[(bits >> (5 * i)) & 31] for i in range(24, -1, -1))
    return "-".join(chars[i : i + 5] for i in range(0, 25, 5))


def normalise_code(text: str) -> str:
    """Case, spaces and dashes are ignored; O reads as 0, and I and L as 1."""
    kept = (c for c in text.upper() if not c.isspace() and c != "-")
    return "".join(_READS_AS.get(c, c) for c in kept)


def last_group(code: str) -> str:
    return normalise_code(code)[-5:]


# key.json files --------------------------------------------------------------------------------


def read_doc(path: Path) -> dict | None:
    """A key.json, or None when it is missing or unreadable."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def write_doc(path: Path, doc: dict) -> None:
    """Written whole or not at all. Raises `OSError`."""
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(doc), encoding="utf-8")
    os.replace(temporary, path)


def ensure_key_doc(
    folder: Path, project_id: str, key: bytes, *, confidential: bool, escrow: Escrow | None
) -> dict | None:
    """The key.json a project's folder should hold, written when it is missing or stale.

    A Confidential Project keeps its code wrap only, and is never wrapped by the Backup key:
    without one, None. Otherwise a wrap by this computer's Backup key. Raises `OSError` and
    `KeyringError`."""
    path = Path(folder) / KEY_FILE
    doc = read_doc(path)
    if confidential:
        return doc if doc is not None and doc.get("kind") == KIND_CODE else None
    current = ensure_backup_key(escrow)
    if doc is None or doc.get("kind") != KIND_KEY or doc.get("key_id") != key_id(current):
        doc = wrap(key, project_id=project_id, backup_key=current)
        write_doc(path, doc)
    return doc


def recover(doc: dict | None, escrow: Callable[[], Escrow | None]) -> bytes:
    """The key in a key.json wrapped by the Backup key, with this computer's Backup key (current
    or kept) or the account's (`escrow`, asked only when this computer has not got it; it becomes
    this computer's when there is none). Raises `RecordsError` PROJECT_KEY_MISSING (no Backup key
    wrap, as for a Confidential Project), `BackupError` BACKUP_NEEDS_SIGN_IN or BACKUP_KEY_WRONG,
    and `KeyringError`."""
    if doc is None or doc.get("kind") != KIND_KEY:
        raise RecordsError(copy.PROJECT_KEY_MISSING)
    wanted = str(doc.get("key_id"))
    found = known_key(wanted)
    account = escrow() if found is None else None
    if account is not None:
        try:
            kept = account.get()
        except Exception as e:  # noqa: BLE001 - offline: the engineer is told what is needed
            log.warning("The Backup key escrow failed (%s)", type(e).__name__)
            kept = None
        if kept is not None and key_id(kept) == wanted:
            found = kept
            if backup_key() is None:
                set_backup_key(kept)
    if found is None:
        raise BackupError(copy.BACKUP_NEEDS_SIGN_IN)
    return unwrap(doc, backup_key=found)


def _key_files(data_dir: Path, base: Path | None) -> list[Path]:
    data_dir = Path(data_dir)
    found = list((data_dir / "projects").glob(f"*/{KEY_FILE}"))
    found += list((data_dir / "snapshots").glob(f"*/{KEY_FILE}"))
    found += [data_dir / "engineer" / KEY_FILE]
    if base is not None:
        found += list(base.glob(f"*/{KEY_FILE}"))
    return [p for p in found if p.is_file()]


def adopt_backup_key(new: bytes, data_dir: Path, backup_root: Path | None) -> int:
    """`new` becomes this computer's Backup key, and every key.json wrapped by the old one (local,
    local snapshots and the backup folder) is wrapped again with it. The old key is kept in the
    key store under its id until every file is done. Returns how many files were wrapped again."""
    from qsone.backup import store  # store imports this module

    old = backup_key()
    if old is not None and old != new:
        keep_key(old)
    set_backup_key(new)
    new_id = key_id(new)
    base = store.base(backup_root) if backup_root is not None else None
    done = failed = 0
    for path in _key_files(data_dir, base):
        doc = read_doc(path)
        if doc is None or doc.get("kind") != KIND_KEY or doc.get("key_id") == new_id:
            continue
        found = known_key(str(doc.get("key_id")))
        if found is None:
            continue  # wrapped by a key this computer never had
        try:
            key = unwrap(doc, backup_key=found)
            write_doc(path, wrap(key, project_id=str(doc["project_id"]), backup_key=new))
            done += 1
        except (BackupError, OSError):
            failed += 1
    if old is not None and old != new and not failed:
        keyring.delete_password(SERVICE, f"{KEY_USER}:{key_id(old)}")
    log.info("Backup key adopted: %d key files wrapped again, %d failed", done, failed)
    return done
