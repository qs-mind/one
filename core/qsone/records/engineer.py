"""The Engineer Records file at `<data>/engineer/`: one per data folder, with a key of its own.

Its key is kept in the key store under "project:engineer-<id>", where <id> is 32 random hex
digits made with the file. The id is kept twice: in the file's meta (`engineer_id`) and in a
plain file next to it, `engineer/id`, which is read before the file can be opened. Until 5 Nov
2026 every data folder kept this key under "project:engineer", so a core started with another
data folder (a smoke test, a second copy of One) wrote over the key of every other folder's file.

Opening, in this order:
- With `id`: the file opens with its own key.
- Without `id` (a file from before): the key under the old name is tried, and when it opens the
  file it is copied to a new id's name. The old entry stays: another data folder on this
  computer may still need it to move its own file.
- A key that is missing or does not open the file is looked for in `key.json` (the key wrapped
  by the Backup key, as for a project).
- Still closed: the file, its key.json and its id are kept aside as `<name>.unreadable-<date>`,
  never deleted, and a new file is made. The logs name ids only.

A backup copies the file under the id "engineer"; a restore keeps the id in its meta."""

import logging
import os
import re
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from keyring.errors import KeyringError

from qsone import copy
from qsone.backup import keys
from qsone.backup.keys import BackupError, Escrow
from qsone.records import audit, vault
from qsone.records.project import FILE_NAME, Records, RecordsError

log = logging.getLogger(__name__)

FOLDER = "engineer"
NAME = "Engineer Records"
ACTOR = "engineer"
ID_FILE = "id"
META = "engineer_id"
OLD_KEY_ID = FOLDER  # the one key store name every data folder shared before 5 Nov 2026
_ID = re.compile(r"[0-9a-f]{32}")
_CLOSED = (copy.PROJECT_KEY_MISSING, copy.PROJECT_DAMAGED)


def key_id(engineer_id: str) -> str:
    return f"{FOLDER}-{engineer_id}"


def read_id(folder: Path) -> str | None:
    try:
        text = (Path(folder) / ID_FILE).read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return text if _ID.fullmatch(text) else None


def write_id(folder: Path, engineer_id: str) -> None:
    """Written whole or not at all. Raises `OSError`."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f"{ID_FILE}.part"
    temporary.write_text(engineer_id, encoding="ascii")
    os.replace(temporary, folder / ID_FILE)


def open_records(data_dir: Path, escrow: Callable[[], Escrow | None] = lambda: None) -> Records:
    """Opens this data folder's Engineer Records, making them on first use, moving a file from
    before to its own key, or keeping an unreadable file aside and starting afresh (see above).
    Raises `RecordsError`: KEY_STORE_DOWN (503) or TOO_NEW. Close it when done."""
    folder = Path(data_dir) / FOLDER
    try:
        if not (folder / FILE_NAME).is_file():
            _set_aside(folder, read_id(folder))  # what a file left (its key.json) stays
            return _create(folder, escrow)
        engineer_id = read_id(folder)
        try:
            if engineer_id is not None:
                return Records.open(folder, key_id=key_id(engineer_id))
            key = vault.get_key(OLD_KEY_ID)
            rec = Records.open(folder, key_id=OLD_KEY_ID, key=key)
            log.info("Engineer Records opened with the old key name: moving them")
        except RecordsError as e:
            if not any(e.text is text for text in _CLOSED):
                raise
            found = _from_key_doc(folder, escrow)
            if found is None:
                _set_aside(folder, engineer_id)
                return _create(folder, escrow)
            rec, key = found
        assert key is not None
        return _settle(rec, key, escrow)
    except KeyringError:
        raise RecordsError(copy.PROJECT_KEY_STORE_DOWN, status=503) from None


def _create(folder: Path, escrow: Callable[[], Escrow | None]) -> Records:
    engineer_id = uuid4().hex
    write_id(folder, engineer_id)  # first: a file is never left without its id
    rec = Records.create(
        folder, name=NAME, actor=ACTOR, key_id=key_id(engineer_id), meta={META: engineer_id}
    )
    key = vault.get_key(rec.key_id)
    if key is not None:
        _key_doc(rec, key, escrow)
    log.info("Engineer Records made: %s", engineer_id)
    return rec


def _from_key_doc(
    folder: Path, escrow: Callable[[], Escrow | None]
) -> tuple[Records, bytes] | None:
    """The file opened with the key in its key.json, or None when that cannot be done."""
    try:
        key = keys.recover(keys.read_doc(folder / keys.KEY_FILE), escrow)
        rec = Records.open(folder, key=key)
    except (BackupError, RecordsError) as e:
        log.warning("Engineer Records: key.json did not open them (%s)", type(e).__name__)
        return None
    log.warning("Engineer Records opened with the key from key.json")
    return rec, key


def _settle(rec: Records, key: bytes, escrow: Callable[[], Escrow | None]) -> Records:
    """A file opened with a key found elsewhere (the old name or key.json): the key goes under
    the file's own id, then `id` is written. Raises `KeyringError`, `OSError`."""
    try:
        engineer_id = rec.meta().get(META) or _new_id(rec)
        vault.put_key(key_id(engineer_id), key)
        write_id(rec.folder, engineer_id)
    except BaseException:
        rec.close()
        raise
    rec.key_id = key_id(engineer_id)
    _key_doc(rec, key, escrow)
    log.warning("Engineer Records moved to their own key: %s", engineer_id)
    return rec


def _new_id(rec: Records) -> str:
    engineer_id = uuid4().hex
    with rec.write(ACTOR, upkeep=True) as conn:
        rec.set_meta(conn, META, engineer_id)
        audit.record(
            conn,
            at=rec.clock(),
            actor=ACTOR,
            action="update",
            table="meta",
            row_id=META,
            before=None,
            after={META: engineer_id},
        )
    return engineer_id


def _key_doc(rec: Records, key: bytes, escrow: Callable[[], Escrow | None]) -> None:
    """key.json, so a lost key can come back: kept only when it holds this very key (before 5 Nov
    2026 a backup could wrap another folder's key). A failure is logged, never raised."""
    try:
        current = keys.ensure_backup_key(escrow())
        path = rec.folder / keys.KEY_FILE
        doc = keys.read_doc(path)
        with suppress(BackupError):
            if doc is not None and keys.unwrap(doc, backup_key=current) == key:
                return
        keys.write_doc(path, keys.wrap(key, project_id=FOLDER, backup_key=current))
    except (OSError, KeyringError) as e:
        log.warning("Engineer Records: key.json not written (%s)", type(e).__name__)


def _set_aside(folder: Path, engineer_id: str | None) -> None:
    """The unreadable file and what belongs to it (or what a missing file left behind) are
    renamed, never deleted. Raises `OSError`."""
    names = (FILE_NAME, f"{FILE_NAME}-wal", f"{FILE_NAME}-shm", keys.KEY_FILE, ID_FILE)
    found = [name for name in names if (folder / name).exists()]
    if not found or found == [ID_FILE]:  # nothing, or only the id a failed start left
        return
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    stamp, n = f"unreadable-{day}", 1
    while any((folder / f"{name}.{stamp}").exists() for name in names):
        n += 1
        stamp = f"unreadable-{day}-{n}"
    for name in found:
        if name.startswith(f"{FILE_NAME}-"):  # SQLite finds a WAL file by the database's name
            aside = folder / f"{FILE_NAME}.{stamp}{name.removeprefix(FILE_NAME)}"
        else:
            aside = folder / f"{name}.{stamp}"
        os.replace(folder / name, aside)
    log.warning("Engineer Records %s kept aside (%s): %s", engineer_id or "-", stamp, found)
