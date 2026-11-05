"""Backup copies on disk: `<folder>/QS Mind One Backup/<project id>/<UTC time>.db` plus `key.json`,
and `engineer/` the same way. Every name is an id or a time, so nothing in the folder is
readable. A copy is encrypted with the project's own key; its `key.json` holds that key wrapped
by the Backup key, or by the project's recovery code for a Confidential Project. Log ids only."""

import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from keyring.errors import KeyringError

from qsone import copy
from qsone.backup import keys
from qsone.backup.keys import BackupError
from qsone.records import db, engineer, vault
from qsone.records.project import FILE_NAME, Records

log = logging.getLogger(__name__)

BACKUP_DIR = "QS Mind One Backup"  # not "ONE": Linux would no longer find the backups made before
ENGINEER = engineer.FOLDER  # the Engineer Records folder, backed up as one more id
_ID = re.compile(r"[0-9a-f]{32}")
_STAMP = "%Y-%m-%dT%H%M%SZ"  # no colons: a valid file name on every system


@dataclass(frozen=True)
class Found:
    id: str
    name: str | None
    last_backup: str
    needs: str | None  # None, "sign_in", "backup_code" or "project_code"


def is_id(name: str) -> bool:
    return name == ENGINEER or _ID.fullmatch(name) is not None


def base(root: Path) -> Path:
    """The backup folder inside the folder the engineer picked (or that folder itself)."""
    root = Path(root)
    return root if root.name == BACKUP_DIR else root / BACKUP_DIR


def _stamp(now: str) -> str:
    return datetime.fromisoformat(now).astimezone(UTC).strftime(_STAMP)


def _time(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.stem, _STAMP).replace(tzinfo=UTC)
    except ValueError:
        return None


def _iso(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def _copies(folder: Path) -> list[tuple[datetime, Path]]:
    """The finished copies in a project's backup folder, newest first."""
    found = [(t, p) for p in folder.glob("*.db") if (t := _time(p)) is not None]
    return sorted(found, reverse=True)


def _remove(part: Path) -> None:
    for path in (part, *(part.with_name(part.name + s) for s in ("-wal", "-shm", "-journal"))):
        path.unlink(missing_ok=True)


def _name(path: Path, key: bytes, field: str = "name") -> str:
    """Opens a copy read-only, checks it, and gives the project's name (or another meta field,
    "" when it has none). Raises `DatabaseError`."""
    conn = db.connect(path, key, readonly=True)
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] < 1:
            raise db.DatabaseError("no schema")
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (field,)).fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


def snapshot(rec: Records, dest: Path, key: bytes, *, now: str) -> Path:
    """One copy of `rec` into `dest`, with SQLite's online backup API under the Records lock.
    It is written as `<time>.db.part`, opened to check, then renamed. The copy is a single file
    (rollback journal, no WAL), so a synced folder never holds half of one. Raises `OSError` or
    `DatabaseError`; then no part is left behind."""
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / f"{_stamp(now)}.db"
    part = final.with_name(final.name + ".part")
    _remove(part)
    try:
        out = db.connect(part, key)
        try:
            with rec.read() as conn:
                try:
                    conn.backup(out)
                except db.DatabaseError as e:  # the copy failed, not the project
                    raise OSError("the backup copy failed") from e
            out.execute("PRAGMA journal_mode = DELETE")
        finally:
            out.close()
        _name(part, key)
        os.replace(part, final)
    except BaseException:
        _remove(part)
        raise
    return final


def prune(dest: Path, now: datetime, keep_last: int = 10, daily_days: int = 30) -> list[Path]:
    """Keeps the newest `keep_last` copies plus the newest of each of the last `daily_days`
    days (today included); removes the rest and returns them."""
    copies = _copies(dest)
    keep = {p for _, p in copies[:keep_last]}
    today = now.astimezone(UTC).date()
    first = today - timedelta(days=daily_days - 1)
    days: set = set()
    for at, path in copies:
        day = at.date()
        if first <= day <= today and day not in days:
            days.add(day)
            keep.add(path)
    removed = [p for _, p in copies if p not in keep]
    for path in removed:
        path.unlink(missing_ok=True)
    return removed


def _known(wanted_id: str) -> bytes | None:
    try:
        return keys.known_key(wanted_id)
    except KeyringError:
        return None


def _backup_key_for(doc: dict, backup_key: bytes | None) -> bytes | None:
    wanted = str(doc.get("key_id"))
    if backup_key is not None and keys.key_id(backup_key) == wanted:
        return backup_key
    return _known(wanted)


def _needs(doc: dict, backup_key: bytes | None, code_doc: dict | None) -> str | None:
    if doc.get("kind") == keys.KIND_CODE:
        return "project_code"
    if _backup_key_for(doc, backup_key) is not None:
        return None
    if code_doc is not None and code_doc.get("key_id") == doc.get("key_id"):
        return "backup_code"
    return "sign_in"


def found(root: Path, *, backup_key: bytes | None) -> list[Found]:
    """The projects in a backup folder, each with what it needs to be restored. A name is read
    only from a copy this computer can open. A folder with no backups gives an empty list."""
    folder = base(root)
    if not folder.is_dir():
        return []
    code_doc = keys.read_doc(folder / keys.BACKUP_KEY_FILE)
    listed = []
    for project in sorted(folder.iterdir()):
        if not (project.is_dir() and is_id(project.name)):
            continue
        doc, copies = keys.read_doc(project / keys.KEY_FILE), _copies(project)
        if doc is None or not copies:
            continue
        needs, name = _needs(doc, backup_key, code_doc), None
        if needs is None:
            try:
                key = keys.unwrap(doc, backup_key=_backup_key_for(doc, backup_key))
                name = _name(copies[0][1], key)
            except (BackupError, db.DatabaseError, OSError):
                name = None
        listed.append(Found(project.name, name, _iso(copies[0][0]), needs))
    return listed


def _project_key(
    doc: dict, folder: Path, backup_key: bytes | None, code: str | None
) -> tuple[bytes, bytes | None]:
    """The project key from a backup's key.json, and the Backup key that opened it."""
    if doc.get("kind") == keys.KIND_CODE:
        return keys.unwrap(doc, code=code), None
    found_key = _backup_key_for(doc, backup_key)
    code_doc = keys.read_doc(folder / keys.BACKUP_KEY_FILE)
    has_code = code_doc is not None and code_doc.get("key_id") == doc.get("key_id")
    if found_key is None and has_code and code:
        assert code_doc is not None
        found_key = keys.unwrap(code_doc, code=code)
    if found_key is None:
        raise BackupError(copy.BACKUP_NEEDS_CODE if has_code else copy.BACKUP_NEEDS_SIGN_IN)
    return keys.unwrap(doc, backup_key=found_key), found_key


def target(data_dir: Path, project_id: str) -> Path:
    """Where a project (or the Engineer Records) lives on this computer."""
    data_dir = Path(data_dir)
    return data_dir / ENGINEER if project_id == ENGINEER else data_dir / "projects" / project_id


def restore(
    root: Path, project_id: str, data_dir: Path, *, backup_key: bytes | None, code: str | None
) -> str:
    """Puts the newest copy of a project back in `data_dir` under the same id, with its key in
    the key store and its key.json, and returns its name. The project must be closed here.
    Raises `BackupError` (what is needed, or a wrong key or code), `KeyringError`, `OSError`."""
    if not is_id(project_id):
        raise BackupError(copy.PROJECT_NOT_FOUND, status=404)
    folder = base(root)
    source = folder / project_id
    doc, copies = keys.read_doc(source / keys.KEY_FILE), _copies(source)
    if doc is None or not copies:
        raise BackupError(copy.PROJECT_NOT_FOUND, status=404)
    key, opened_by = _project_key(doc, folder, backup_key, code)
    home = target(data_dir, project_id)
    home.mkdir(parents=True, exist_ok=True)
    part = home / f"{FILE_NAME}.part"
    _remove(part)
    try:
        shutil.copyfile(copies[0][1], part)
        try:
            name = _name(part, key)
        except db.DatabaseError:
            raise BackupError(copy.PROJECT_DAMAGED) from None
        if project_id == ENGINEER:  # its key goes under the id in its meta (a new one if none)
            engineer_id = _name(part, key, engineer.META) or uuid4().hex
            vault.put_key(engineer.key_id(engineer_id), key)
        else:
            vault.put_key(project_id, key)
        for side in ("-wal", "-shm", "-journal"):
            (home / f"{FILE_NAME}{side}").unlink(missing_ok=True)
        os.replace(part, home / FILE_NAME)
    except BaseException:
        _remove(part)
        raise
    if project_id == ENGINEER:
        engineer.write_id(home, engineer_id)
    if doc.get("kind") == keys.KIND_CODE:
        keys.write_doc(home / keys.KEY_FILE, doc)  # a Confidential Project keeps its code wrap
    else:
        assert opened_by is not None
        local = keys.backup_key()
        if local is None:  # a new computer: the key that opened the backup becomes its own
            keys.set_backup_key(opened_by)
            local = opened_by
        elif local != opened_by:  # other projects in this folder still open without a code
            keys.keep_key(opened_by)
        keys.write_doc(
            home / keys.KEY_FILE, keys.wrap(key, project_id=project_id, backup_key=local)
        )
    log.info("Restored %s from a backup", project_id)
    return name
