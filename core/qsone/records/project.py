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
    """A refusal the engineer can read: `text` is an {en, ar} pair from `copy`."""

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

    def __init__(self, folder: Path, conn: db.Connection, key_id: str | None = None):
        self.id = folder.name
        self.folder = folder
        self.key_id = key_id or folder.name  # the key's id in the key store (`vault`)
        self.clock: Callable[[], str] = utc_now
        self._conn: db.Connection | None = conn
        self._lock = threading.RLock()
        self._depth = 0  # how many `write` blocks are open; only the lock's holder changes it
        self.archived_at: str | None = None  # meta.archived_at, read at open (Plan 8)

    @classmethod
    def create(
        cls,
        folder: Path,
        *,
        name: str,
        actor: str,
        key_id: str | None = None,
        meta: dict[str, str] | None = None,
    ) -> "Records":
        """Makes a new project in `folder`, which must not exist yet. The Engineer Records pass
        their own `key_id` and `meta`, and may reuse their folder (`records/engineer.py`).

        Raises `KeyringError` when the key store is down; then nothing new exists. On any other
        failure what this made (the folder, or only the file in a folder that was there) and the
        key are removed before the error is raised."""
        if folder.exists() and (key_id is None or (folder / FILE_NAME).exists()):
            raise FileExistsError(folder)
        project_id = folder.name
        key_id = key_id or project_id
        made = not folder.exists()
        key = vault.create_key(key_id)
        rec = None
        try:
            folder.mkdir(parents=True, exist_ok=True)
            rec = cls(folder, db.connect(folder / FILE_NAME, key), key_id)
            rec._migrate()
            at = rec.clock()
            meta = {
                "project_id": project_id,
                "name": name,
                "created_at": at,
                "created_by": actor,
                **(meta or {}),
            }
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
            if made:
                shutil.rmtree(folder, ignore_errors=True)
            else:
                for side in ("", "-wal", "-shm", "-journal"):
                    with suppress(OSError):
                        (folder / f"{FILE_NAME}{side}").unlink(missing_ok=True)
            with suppress(KeyringError):
                vault.delete_key(key_id)
            raise
        return rec

    @classmethod
    def open(
        cls, folder: Path, *, key_id: str | None = None, key: bytes | None = None
    ) -> "Records":
        """Opens with the key kept under `key_id` (the folder's name by default), or with `key`
        when it is given (then the key store is not read).

        Raises `RecordsError`: NOT_FOUND, KEY_STORE_DOWN, KEY_MISSING, DAMAGED or TOO_NEW."""
        path = folder / FILE_NAME
        if not path.is_file():
            raise RecordsError(copy.PROJECT_NOT_FOUND, status=404)
        key_id = key_id or folder.name
        if key is None:
            try:
                key = vault.get_key(key_id)
            except KeyringError:
                raise RecordsError(copy.PROJECT_KEY_STORE_DOWN, status=503) from None
        if key is None:
            raise RecordsError(copy.PROJECT_KEY_MISSING)
        try:
            rec = cls(folder, db.connect(path, key), key_id)
        except db.DatabaseError as e:
            raise RecordsError(copy.PROJECT_DAMAGED) from e
        try:
            rec._migrate()
            rec.archived_at = rec.meta().get("archived_at")
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
            conn.execute("PRAGMA foreign_keys = OFF")
            try:
                conn.executescript(
                    f"BEGIN IMMEDIATE;\n{body}\nPRAGMA user_version = {len(migrations)};"
                )
                if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise RecordsError(copy.PROJECT_DAMAGED)
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.execute("PRAGMA foreign_keys = ON")

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
    def write(
        self, actor: str, *, archive_change: bool = False, upkeep: bool = False
    ) -> Iterator[db.Connection]:
        """One transaction: commits when the block ends, rolls back if it raises.

        Write the audit rows for the change inside the same block, with this actor. A `write`
        inside another on the same thread joins it through `SAVEPOINT w<depth>`: when the inner
        block raises, only its own work is rolled back; nothing is kept until the outer block
        commits. The inner block's audit rows carry its own actor.

        While the project is archived, an outer `write` is refused with PROJECT_ARCHIVED (423),
        except the archive change itself (`archive_change`) and `upkeep` that changes no project
        data: the search index and the open-document state, so reading and searching still work."""
        if not actor.strip():
            raise ValueError("every change needs an actor")
        with self._lock:
            conn = self._connection()
            if self._depth:
                yield from self._savepoint(conn)
                return
            if self.archived_at is not None and not (archive_change or upkeep):
                raise RecordsError(copy.PROJECT_ARCHIVED, status=423)
            conn.execute("BEGIN IMMEDIATE")
            self._depth = 1
            try:
                yield conn
                conn.execute("COMMIT")
            except db.DatabaseError as e:
                if type(e) is not db.DatabaseError:
                    self._rollback(conn)
                    raise
                raise self._damaged() from e
            except BaseException:
                self._rollback(conn)
                raise
            finally:
                self._depth = 0

    def _savepoint(self, conn: db.Connection) -> Iterator[db.Connection]:
        """The inner `write`: under the lock, inside the outer transaction."""
        depth = self._depth
        name = f"w{depth}"
        conn.execute(f"SAVEPOINT {name}")
        self._depth = depth + 1
        try:
            yield conn
            conn.execute(f"RELEASE {name}")
        except db.DatabaseError as e:
            if type(e) is not db.DatabaseError:
                self._undo_savepoint(conn, name)
                raise
            raise self._damaged() from e
        except BaseException:
            self._undo_savepoint(conn, name)
            raise
        finally:
            self._depth = depth

    def _undo_savepoint(self, conn: db.Connection, name: str) -> None:
        if self._conn is not None and conn.in_transaction:
            conn.execute(f"ROLLBACK TO {name}")
            conn.execute(f"RELEASE {name}")

    def _rollback(self, conn: db.Connection) -> None:
        if self._conn is not None and conn.in_transaction:  # damage found inside closes it
            conn.execute("ROLLBACK")

    @property
    def is_open(self) -> bool:
        """False after `close`, which `read` and `write` also do when they find damage."""
        return self._conn is not None

    def close(self) -> None:
        """Safe to call twice."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
