"""Files in Project Records. The original is kept inside the encrypted file in pieces, found again
by its SHA-256; its text goes in chunks and into the word index. A file dropped again under the same
name with new content is a new version; the old one is kept and marked "valid until"."""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass

from qsone import copy
from qsone.records import audit, search
from qsone.records.arabic import NORMALISER_VERSION
from qsone.records.extract import chunk, extract
from qsone.records.project import Records, RecordsError

MAX_FILE_BYTES = 256 * 1024 * 1024
PIECE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class FileInfo:
    id: str
    name: str
    kind: str
    size: int
    sha256: str
    status: str
    note: str | None  # name of a copy.py text
    pages: int | None
    chunks: int
    added_at: str
    replaces: str | None
    valid_until: str | None
    duplicate: bool = False


_INFO = (
    "SELECT f.id, f.name, f.kind, f.size, f.sha256, f.status, f.note, f.pages,"
    " (SELECT count(*) FROM chunks c WHERE c.file_id = f.id), f.added_at, f.replaces,"
    " f.valid_until FROM files f"
)


def _same_bytes(conn, sha256: str) -> FileInfo | None:
    row = conn.execute(
        f"{_INFO} WHERE f.sha256 = ? ORDER BY f.valid_until IS NOT NULL, f.rowid DESC LIMIT 1",
        (sha256,),
    ).fetchone()
    return None if row is None else FileInfo(*row, duplicate=True)


def add_file(
    rec: Records, name: str, data: bytes, *, actor: str, embedder: search.Embedder | None = None
) -> FileInfo:
    """Raises `RecordsError`: FILE_EMPTY (422) or FILE_TOO_BIG (413), and then nothing is stored.

    `name` is display text only and never touches the disk."""
    name = re.split(r"[/\\]", name)[-1][:255]
    if not data:
        raise RecordsError(copy.FILE_EMPTY, status=422)
    if len(data) > MAX_FILE_BYTES:
        raise RecordsError(copy.FILE_TOO_BIG, status=413)
    sha256 = hashlib.sha256(data).hexdigest()
    with rec.read() as conn:
        found = _same_bytes(conn, sha256)
    if found is not None:
        return found

    extracted = extract(name, data)  # outside the lock: reading a big file takes time
    chunks = chunk(extracted.pieces)
    file_id = uuid.uuid4().hex
    with rec.write(actor) as conn:
        found = _same_bytes(conn, sha256)  # the same bytes may have come in meanwhile
        if found is not None:
            return found
        at = rec.clock()
        conn.executemany(
            "INSERT INTO file_pieces(sha256, seq, data) VALUES (?, ?, ?)",
            (
                (sha256, seq, data[start : start + PIECE_BYTES])
                for seq, start in enumerate(range(0, len(data), PIECE_BYTES))
            ),
        )
        old = conn.execute(
            "SELECT id FROM files WHERE name = ? AND valid_until IS NULL", (name,)
        ).fetchone()
        replaces = None if old is None else old[0]
        if replaces is not None:
            conn.execute("UPDATE files SET valid_until = ? WHERE id = ?", (at, replaces))
            audit.record(
                conn,
                at=at,
                actor=actor,
                action="replace",
                table="files",
                row_id=replaces,
                before={"valid_until": None},
                after={"valid_until": at, "replaced_by": file_id},
            )
        row = {
            "id": file_id,
            "name": name,
            "kind": extracted.kind,
            "size": len(data),
            "sha256": sha256,
            "status": extracted.status,
            "note": extracted.note,
            "pages": extracted.pages,
            "added_at": at,
            "added_by": actor,
            "replaces": replaces,
        }
        conn.execute(
            "INSERT INTO files(id, name, kind, size, sha256, status, note, pages, added_at,"
            " added_by, replaces) VALUES (:id, :name, :kind, :size, :sha256, :status, :note,"
            " :pages, :added_at, :added_by, :replaces)",
            row,
        )
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="create",
            table="files",
            row_id=file_id,
            before=None,
            after=row,
        )
        indexed = []
        for seq, piece in enumerate(chunks):
            cur = conn.execute(
                "INSERT INTO chunks(file_id, seq, locator, text) VALUES (?, ?, ?, ?)",
                (file_id, seq, json.dumps(piece.locator, ensure_ascii=False), piece.text),
            )
            indexed.append((cur.lastrowid, piece.text))
        search.index_words(conn, indexed)
        # Set only when missing: an older version stays, so `ensure_index` still rebuilds it.
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('normaliser_version', ?)"
            " ON CONFLICT(key) DO NOTHING",
            (str(NORMALISER_VERSION),),
        )
    if embedder is not None:
        search.index_vectors(rec, embedder)
    return FileInfo(
        file_id,
        name,
        extracted.kind,
        len(data),
        sha256,
        extracted.status,
        extracted.note,
        extracted.pages,
        len(chunks),
        at,
        replaces,
        None,
    )


def list_files(rec: Records, *, include_old: bool = False) -> list[FileInfo]:
    """Newest first; current versions only unless `include_old`."""
    with rec.read() as conn:
        rows = conn.execute(
            f"{_INFO} WHERE ? OR f.valid_until IS NULL ORDER BY f.rowid DESC", (include_old,)
        ).fetchall()
    return [FileInfo(*row) for row in rows]


def read_original(rec: Records, file_id: str) -> bytes:
    """The file exactly as it was dropped. Raises `KeyError` for an unknown id."""
    with rec.read() as conn:
        row = conn.execute("SELECT sha256 FROM files WHERE id = ?", (file_id,)).fetchone()
        if row is None:
            raise KeyError(file_id)
        pieces = conn.execute(
            "SELECT data FROM file_pieces WHERE sha256 = ? ORDER BY seq", row
        ).fetchall()
    return b"".join(data for (data,) in pieces)
