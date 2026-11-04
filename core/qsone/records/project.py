"""One project: a folder named by its id, holding one encrypted file, `records.db`.

The folder's name is the project id; the caller picks it at random (`uuid4().hex`). The key is
found by that id in the system key store, so nothing about the project is readable on disk.
"""

import shutil
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from keyring.errors import KeyringError

from qsone import copy
from qsone.records import audit, db, schema, vault

FILE_NAME = "records.db"


class RecordsError(Exception):
    """A refusal the engineer can read: `text` is an {en, ar} pair from `copy.py`."""

    def __init__(self, text: dict[str, str], status: int = 409, field: str | None = None):
        super().__init__(text["en"])
        self.text = text
        self.status = status
        self.field = field


def utc_now() -> str:
    """UTC ISO-8601 with microseconds, e.g. 2026-11-04T08:00:00.000000+00:00."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Records:
    """An open project. One connection, serialised by a lock. Close it when done."""

    def __init__(self, folder: Path, conn: db.Connection):
        self.id = folder.name
        self.folder = folder
        self.clock: Callable[[], str] = utc_now
        self._conn: db.Connection | None = conn
        self._lock = threading.RLock()

    @classmethod
    def create(cls, folder: Path, *, name: str, actor: str) -> "Records":
        """Makes a new project in `folder`, which must not exist yet.

        Raises `KeyringError` when the key store is down; then nothing exists. On any other
        failure the folder and the key are removed before the error is raised."""
        if folder.exists():
            raise FileExistsError(folder)
        project_id = folder.name
        key = vault.create_key(project_id)
        rec = None
        try:
            folder.mkdir(parents=True)
            rec = cls(folder, db.connect(folder / FILE_NAME, key))
            rec._migrate()
            at = rec.clock()
            meta = {"project_id": project_id, "name": name, "created_at": at, "created_by": actor}
            with rec.write(actor) as conn:
                for k, v in meta.items():
                    rec.set_meta(conn, k, v)
                audit.record(
                    conn,
                    at=at,
                    actor=actor,
                    action="create",
                    table="meta",
                    row_id=project_id,
                    before=None,
                    after=meta,
                )
        except BaseException:
            if rec is not None:
                rec.close()
            shutil.rmtree(folder, ignore_errors=True)
            with suppress(KeyringError):
                vault.delete_key(project_id)
            raise
        return rec

    @classmethod
    def open(cls, folder: Path) -> "Records":
        """Raises `RecordsError`: NOT_FOUND, KEY_MISSING, DAMAGED or TOO_NEW."""
        path = folder / FILE_NAME
        if not path.is_file():
            raise RecordsError(copy.PROJECT_NOT_FOUND, status=404)
        try:
            key = vault.get_key(folder.name)
        except KeyringError:
            key = None
        if key is None:
            raise RecordsError(copy.PROJECT_KEY_MISSING)
        try:
            rec = cls(folder, db.connect(path, key))
        except db.DatabaseError as e:
            raise RecordsError(copy.PROJECT_DAMAGED) from e
        try:
            rec._migrate()
            rec.meta()
        except db.DatabaseError as e:
            rec.close()
            raise RecordsError(copy.PROJECT_DAMAGED) from e
        except BaseException:
            rec.close()
            raise
        return rec

    def _migrate(self) -> None:
        """Applies the missing migrations in one transaction; refuses a file from a newer One."""
        migrations = schema.MIGRATIONS
        with self._lock:
            conn = self._connection()
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > len(migrations):
                raise RecordsError(copy.PROJECT_TOO_NEW)
            if version == len(migrations):
                return
            body = "\n".join(f"{sql};" for sql in migrations[version:])
            try:
                conn.executescript(
                    f"BEGIN IMMEDIATE;\n{body}\nPRAGMA user_version = {len(migrations)};\nCOMMIT;"
                )
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    def meta(self) -> dict[str, str]:
        with self.read() as conn:
            return dict(conn.execute("SELECT key, value FROM meta"))

    def set_meta(self, conn: db.Connection, key: str, value: str) -> None:
        """Inside `write`."""
        conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _connection(self) -> db.Connection:
        if self._conn is None:
            raise RecordsError(copy.PROJECT_NOT_OPEN)
        return self._conn

    def _damaged(self) -> RecordsError:
        """Opening reads only a few pages, so damage elsewhere shows when a page is read. SQLCipher
        then refuses every later statement on this connection, so it is closed (which also
        discards an open transaction)."""
        self.close()
        return RecordsError(copy.PROJECT_DAMAGED)

    @contextmanager
    def read(self) -> Iterator[db.Connection]:
        with self._lock:
            conn = self._connection()
            try:
                yield conn
            except db.DatabaseError as e:
                if type(e) is not db.DatabaseError:  # constraint, SQL or lock errors
                    raise
                raise self._damaged() from e

    @contextmanager
    def write(self, actor: str) -> Iterator[db.Connection]:
        """One transaction: commits when the block ends, rolls back if it raises.

        Write the audit rows for the change inside the same block, with this actor."""
        if not actor.strip():
            raise ValueError("every change needs an actor")
        with self._lock:
            conn = self._connection()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except db.DatabaseError as e:
                if type(e) is not db.DatabaseError:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
                raise self._damaged() from e
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        """Safe to call twice."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
