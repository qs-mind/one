"""When backups run, where they go, and what the Backup screen shows.

State in settings.json, ids and times only: `backup` = {"folder", "last_run", "last_ok",
"code_key_id", "code_saved"} and `backups` = {<project id>: {"at", "audit_id"}} for the last copy
in the folder. Local snapshots (the newest 3 of each project) are always made in
`<data>/snapshots/`, even with no folder picked. The runner never raises into the app: a failed
copy is logged by id and error class, and tried again next time."""

import logging
import secrets
import shutil
import threading
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from keyring.errors import KeyringError

from qsone import copy, settings
from qsone.backup import keys, store
from qsone.backup.keys import BackupError, Escrow
from qsone.records import db, vault
from qsone.records.project import Records, RecordsError

if TYPE_CHECKING:
    from qsone.projects import Projects

log = logging.getLogger(__name__)

INTERVAL = 30 * 60  # seconds between runs
LOCAL_KEPT = 3
BACKUP_KEY = "backup-key"  # what a confirm is for: the Backup key's code, or a project id
_FAILURES = (OSError, db.DatabaseError, RecordsError, KeyringError)


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store_down() -> RecordsError:
    return RecordsError(copy.PROJECT_KEY_STORE_DOWN, status=503)


class Backups:
    def __init__(
        self,
        data_dir: Path,
        projects: "Projects",
        escrow_factory: Callable[[], Escrow | None] = lambda: None,
        engineer: Callable[[], Records] | None = None,
    ):
        """`engineer` gives the open Engineer Records (the engine holds it); without it the file
        at `<data>/engineer/` is opened for the copy."""
        self.data_dir = Path(data_dir)
        self.projects = projects
        self.escrow_factory = escrow_factory
        self.engineer = engineer
        self.clock: Callable[[], datetime] = lambda: datetime.now(UTC)
        self._lock = threading.RLock()  # one run at a time
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._local: dict[str, int] = {}  # id -> audit id of the newest local snapshot
        self._pending: dict[str, str] = {}  # a code's last group, in memory until confirmed

    # Settings ------------------------------------------------------------------------------------

    def _settings(self) -> dict:
        saved = settings.load().get("backup")
        return saved if isinstance(saved, dict) else {}

    def _save(self, **changes) -> None:
        settings.save("backup", self._settings() | changes)

    def _state(self) -> dict:
        saved = settings.load().get("backups")
        return saved if isinstance(saved, dict) else {}

    def _folder(self) -> Path | None:
        folder = self._settings().get("folder")
        return Path(folder) if isinstance(folder, str) and folder else None

    def escrow(self) -> Escrow | None:
        try:
            return self.escrow_factory()
        except Exception as e:  # noqa: BLE001 - the account is never needed to back up
            log.warning("The Backup key escrow is not available (%s)", type(e).__name__)
            return None

    # The screen ----------------------------------------------------------------------------------

    def status(self) -> dict:
        saved, folder, state = self._settings(), self._folder(), self._state()
        reachable = folder is not None and folder.is_dir()
        try:
            local = keys.backup_key()
        except KeyringError:
            local = None
        in_account = False
        escrow = self.escrow() if local is not None else None
        if escrow is not None:
            try:
                in_account = escrow.get() == local
            except Exception as e:  # noqa: BLE001
                log.warning("The Backup key escrow failed (%s)", type(e).__name__)
        code_saved = (
            local is not None
            and saved.get("code_key_id") == keys.key_id(local)
            and saved.get("code_saved") is True
        )
        note = None
        if folder is not None and not reachable:
            last_ok = saved.get("last_ok")
            note = copy.fill(copy.BACKUP_FOLDER_UNREACHABLE, date=last_ok[:10] if last_ok else "—")
        projects = [
            {
                "id": p["id"],
                "last_backup": (state.get(p["id"]) or {}).get("at"),
                "confidential": p["confidential"],
            }
            for p in self.projects.list()
            if "error" not in p
        ]
        return {
            "folder": str(folder) if folder is not None else None,
            "reachable": reachable,
            "last_run": saved.get("last_run"),
            "note": note,
            "backup_key": {
                "local": local is not None,
                "in_account": in_account,
                "code_saved": code_saved,
            },
            "projects": projects,
        }

    def set_folder(self, path: str) -> dict:
        """An absolute, existing folder that One can write in (a test file is written and
        removed). A new folder starts every project's copies afresh."""
        folder = Path(path)
        refused = BackupError(copy.BACKUP_FOLDER_NOT_WRITABLE, status=400, field="path")
        if not folder.is_absolute() or not folder.is_dir():
            raise refused
        probe = folder / f".qsone-{secrets.token_hex(8)}.tmp"
        try:
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            raise refused from None
        with self._lock:
            if self._folder() != folder:
                settings.save("backups", {})
            self._save(folder=str(folder))
        return self.status()

    # Runs ----------------------------------------------------------------------------------------

    def run(self, project_id: str | None = None, *, reason: str) -> int:
        """Copies each project (or one) whose audit trail grew since its last copy; returns how
        many copies went to the folder. Never raises."""
        with self._lock:
            try:
                return self._run(project_id, reason)
            except Exception as e:  # noqa: BLE001 - a backup never breaks the app
                log.warning("Backup run (%s) failed (%s)", reason, type(e).__name__)
                return 0

    def closing(self, rec: Records) -> None:
        """Projects calls this before it closes a project."""
        with self._lock:
            try:
                self._run_one(rec.id, rec, reason="close")
            except Exception as e:  # noqa: BLE001
                log.warning("Backup on close of %s failed (%s)", rec.id, type(e).__name__)

    def _destination(self) -> Path | None:
        folder = self._folder()
        if folder is None or not folder.is_dir():
            return None
        dest = store.base(folder)
        dest.mkdir(exist_ok=True)
        code_doc = keys.read_doc(self.data_dir / keys.BACKUP_KEY_FILE)
        if code_doc is not None:  # the Backup key's code wrap travels with the backups
            keys.write_doc(dest / keys.BACKUP_KEY_FILE, code_doc)
        return dest

    def _targets(self, project_id: str | None) -> list[str]:
        if project_id is not None:
            return [project_id]
        ids = [p["id"] for p in self.projects.list() if "error" not in p]
        return [store.ENGINEER, *ids]

    def _run(self, project_id: str | None, reason: str) -> int:
        dest = self._destination()
        copies = 0
        for pid in self._targets(project_id):
            if reason == "timer" and self._stopping.is_set():
                break
            try:
                rec, temporary = self._records(pid)
            except _FAILURES as e:
                log.warning("Backup (%s) of %s did not open (%s)", reason, pid, type(e).__name__)
                continue
            if rec is None:
                continue
            try:
                copies += self._copy(pid, rec, dest)
            except _FAILURES as e:
                log.warning("Backup (%s) of %s failed (%s)", reason, pid, type(e).__name__)
            finally:
                if temporary:
                    rec.close()
        changes = {"last_run": _iso(self.clock())}
        if dest is not None:
            changes["last_ok"] = changes["last_run"]
        self._save(**changes)
        log.info("Backup run (%s): %d copies", reason, copies)
        return copies

    def _run_one(self, pid: str, rec: Records, reason: str) -> None:
        copies = self._copy(pid, rec, self._destination())
        log.info("Backup (%s) of %s: %d copies", reason, pid, copies)

    def _records(self, pid: str) -> tuple[Records | None, bool]:
        """The project's Records and whether it was opened just for this copy."""
        if pid == store.ENGINEER:
            if self.engineer is not None:
                return self.engineer(), False
            folder = store.target(self.data_dir, pid)
            if not (folder / "records.db").is_file():
                return None, False
            return Records.open(folder), True
        opened = dict(self.projects.opened())
        if pid in opened:
            return opened[pid], False
        return self.projects.open_file(pid), True

    def _key_doc(self, pid: str, rec: Records, key: bytes) -> dict | None:
        confidential = pid != store.ENGINEER and rec.meta().get("confidential") == "1"
        return keys.ensure_key_doc(
            rec.folder, pid, key, confidential=confidential, escrow=self.escrow()
        )

    def _copy(self, pid: str, rec: Records, dest: Path | None) -> int:
        with rec.read() as conn:
            audit_id = conn.execute("SELECT coalesce(max(id), 0) FROM audit").fetchone()[0]
        key = vault.get_key(pid)
        if key is None:
            return 0
        doc = self._key_doc(pid, rec, key)
        if doc is None:
            log.warning("Backup of %s skipped: its key file is missing", pid)
            return 0
        now = self.clock()
        if self._local.get(pid) != audit_id:
            self._write(rec, self.data_dir / "snapshots" / pid, key, doc, now, LOCAL_KEPT, 0)
            self._local[pid] = audit_id
        if dest is None:
            return 0
        state = self._state()
        if (state.get(pid) or {}).get("audit_id") == audit_id:
            return 0
        self._write(rec, dest / pid, key, doc, now, 10, 30)
        settings.save("backups", self._state() | {pid: {"at": _iso(now), "audit_id": audit_id}})
        return 1

    def _write(
        self, rec: Records, dest: Path, key: bytes, doc: dict, now: datetime, last: int, days: int
    ) -> None:
        store.snapshot(rec, dest, key, now=now.isoformat())
        keys.write_doc(dest / keys.KEY_FILE, doc)
        store.prune(dest, now, keep_last=last, daily_days=days)

    def key_changed(self, pid: str) -> None:
        """A project's key.json changed (Confidential on or off): every copy of it follows now,
        so no backup keeps a wrap the engineer turned off. Never raises."""
        doc = keys.read_doc(store.target(self.data_dir, pid) / keys.KEY_FILE)
        if doc is None:
            return
        places = [self.data_dir / "snapshots" / pid]
        dest = self._destination() if self._folder() is not None else None
        if dest is not None:
            places.append(dest / pid)
        for place in places:
            if (place / keys.KEY_FILE).is_file():
                try:
                    keys.write_doc(place / keys.KEY_FILE, doc)
                except OSError as e:
                    log.warning("Key file of %s not updated (%s)", pid, type(e).__name__)

    # The timer -----------------------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._loop, name="backups", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stopping.wait(INTERVAL):
            self.run(reason="timer")

    def stop(self) -> None:
        """Waits for a running copy to finish."""
        self._stopping.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    # Recovery codes ------------------------------------------------------------------------------

    def new_code(self) -> str:
        """A recovery code for the Backup key, shown once: an engineer without an account restores
        on another computer with it. Only its wrap of the Backup key is written."""
        try:
            current = keys.ensure_backup_key(self.escrow())
        except KeyringError:
            raise _store_down() from None
        code = keys.new_recovery_code()
        doc = keys.wrap_with_code(current, project_id=keys.BACKUP_KEY_WRAP_ID, code=code)
        doc["key_id"] = keys.key_id(current)
        with self._lock:
            keys.write_doc(self.data_dir / keys.BACKUP_KEY_FILE, doc)
            try:
                self._destination()
            except OSError as e:
                log.warning("Backup key file not copied to the folder (%s)", type(e).__name__)
            self._save(code_key_id=doc["key_id"], code_saved=False)
            self._pending[BACKUP_KEY] = keys.last_group(code)
        return code

    def expect(self, which: str, code: str) -> None:
        self._pending[which] = keys.last_group(code)

    def confirm(self, which: str, last: str) -> None:
        """The engineer typed the code's last group. Raises RECOVERY_LAST_GROUP_WRONG."""
        wanted = self._pending.get(which)
        given = keys.normalise_code(last)
        if wanted is None or not secrets.compare_digest(given.encode(), wanted.encode()):
            raise BackupError(copy.RECOVERY_LAST_GROUP_WRONG, status=400, field="last_group")
        del self._pending[which]
        if which == BACKUP_KEY:
            self._save(code_saved=True)

    def set_confidential(self, pid: str, on: bool) -> dict:
        try:
            answer = self.projects.set_confidential(pid, on)
        except KeyringError:
            raise _store_down() from None
        self.key_changed(pid)
        if answer.get("code"):
            self.expect(pid, answer["code"])
        else:
            self._pending.pop(pid, None)
        return answer

    # Restore -------------------------------------------------------------------------------------

    def _restore_key(self) -> bytes | None:
        """This computer's Backup key, or the account's on a computer that has none yet."""
        local = keys.backup_key()
        if local is not None:
            return local
        escrow = self.escrow()
        if escrow is None:
            return None
        try:
            return escrow.get()
        except Exception as e:  # noqa: BLE001
            log.warning("The Backup key escrow failed (%s)", type(e).__name__)
            return None

    @staticmethod
    def _root(path: str) -> Path:
        root = Path(path)
        if not root.is_absolute():
            raise BackupError(copy.BACKUP_FOLDER_NOT_WRITABLE, status=400, field="path")
        return root

    def found(self, path: str) -> list[dict]:
        try:
            listed = store.found(self._root(path), backup_key=self._restore_key())
        except KeyringError:
            raise _store_down() from None
        return [asdict(f) for f in listed]

    def restore(self, path: str, pid: str, code: str | None) -> dict:
        """Restores the newest copy under the same id. A project that exists here is first kept
        as a local snapshot."""
        root = self._root(path)
        if not store.is_id(pid):
            raise BackupError(copy.PROJECT_NOT_FOUND, status=404)
        with self._lock:
            try:
                self._keep_before_restore(pid)
                name = store.restore(
                    root, pid, self.data_dir, backup_key=self._restore_key(), code=code
                )
            except KeyringError:
                raise _store_down() from None
            self.projects.forget(pid)
        return {"id": pid, "name": name}

    def _keep_before_restore(self, pid: str) -> None:
        """A local snapshot of the project as it is here, before a restore replaces it. A file
        that does not open (say, its key is gone) is copied as it is: it is encrypted."""
        home = store.target(self.data_dir, pid)
        if not (home / "records.db").is_file():
            return
        if pid != store.ENGINEER:
            self.projects.close(pid, back_up=False)
        dest, now = self.data_dir / "snapshots" / pid, self.clock()
        rec = None
        try:
            rec, _ = self._records(pid)
            key = vault.get_key(pid)
            if rec is None or key is None:
                raise RecordsError(copy.PROJECT_KEY_MISSING)
            doc = self._key_doc(pid, rec, key) or keys.read_doc(home / keys.KEY_FILE) or {}
            self._write(rec, dest, key, doc, now, LOCAL_KEPT, 0)
        except _FAILURES as e:
            log.warning("Snapshot of %s before restore copied as is (%s)", pid, type(e).__name__)
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(home / "records.db", dest / f"{now.strftime('%Y-%m-%dT%H%M%SZ')}.db")
            if (home / keys.KEY_FILE).is_file():
                shutil.copyfile(home / keys.KEY_FILE, dest / keys.KEY_FILE)
        finally:
            if rec is not None:
                rec.close()  # the engine opens the Engineer Records again when it needs them
        self._local.pop(pid, None)
