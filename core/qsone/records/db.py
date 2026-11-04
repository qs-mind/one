"""The only module that imports SQLCipher. Opens one encrypted project file with a raw key."""

from pathlib import Path

import sqlcipher3.dbapi2 as sqlcipher
import sqlite_vec

Connection = sqlcipher.Connection
DatabaseError = sqlcipher.DatabaseError
IntegrityError = sqlcipher.IntegrityError


def connect(path: Path, key: bytes) -> Connection:
    """Raises `DatabaseError` when the file is damaged or the key does not match.

    The connection is in autocommit mode (`isolation_level=None`): `Records.write` begins and
    ends each transaction itself, and its lock serialises use across threads."""
    conn = sqlcipher.connect(str(path), isolation_level=None, check_same_thread=False)
    try:
        conn.execute("PRAGMA cipher_log_level = NONE")
        conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA cache_size = -65536")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except BaseException:
        conn.close()
        raise
    return conn
