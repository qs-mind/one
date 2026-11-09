"""Files in Project Records. The original is kept inside the encrypted file in pieces, found again
by its SHA-256; its text goes in chunks and into the word index. A file dropped again under the same
name with new content is a new version; the old one is kept and marked "valid until". A scanned
page's text, read later by the engineer's AI from its image, is added with `add_ocr_pages`.

A file from a tender folder keeps its `folder`: the path inside the dropped folder (Plan 8),
display text only, never a path on this computer. Two files of the same name in two folders are
two files; a version replaces only the file of the same name in the same folder."""

import hashlib
import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from qsone import copy
from qsone.records import audit, hidden, search
from qsone.records.arabic import NORMALISER_VERSION, display_text
from qsone.records.extract import EXTRACTOR_VERSION, Piece, chunk, extract
from qsone.records.hidden import Flag
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
    note: str | None  # name of a `copy` text
    pages: int | None
    chunks: int
    added_at: str
    replaces: str | None
    valid_until: str | None
    flags: int = 0  # hidden-text flags (file_flags rows)
    folder: str | None = None  # the path inside a dropped folder, "a/b" (Plan 8)
    flag_kinds: str | None = None  # the flags' kinds, "hidden_rows,hidden_sheet" (sorted)
    duplicate: bool = False


_INFO = (
    "SELECT f.id, f.name, f.kind, f.size, f.sha256, f.status, f.note, f.pages,"
    " (SELECT count(*) FROM chunks c WHERE c.file_id = f.id), f.added_at, f.replaces,"
    " f.valid_until, (SELECT count(*) FROM file_flags g WHERE g.file_id = f.id), f.folder,"
    " (SELECT group_concat(kind) FROM (SELECT DISTINCT g.kind FROM file_flags g"
    " WHERE g.file_id = f.id ORDER BY g.kind))"
    " FROM files f"
)


def _same_bytes(conn, sha256: str) -> FileInfo | None:
    row = conn.execute(
        f"{_INFO} WHERE f.sha256 = ? ORDER BY f.valid_until IS NOT NULL, f.rowid DESC LIMIT 1",
        (sha256,),
    ).fetchone()
    return None if row is None else FileInfo(*row, duplicate=True)


MAX_FOLDER = 1000  # characters of a folder path


def clean_folder(folder: str | None) -> str | None:
    """A folder path as kept: "/" between its parts, no empty, "." or ".." part, None when
    nothing is left. Display text only."""
    if folder is None:
        return None
    parts = (p.strip() for p in re.split(r"[/\\]", folder))
    return "/".join(p for p in parts if p and p not in (".", ".."))[:MAX_FOLDER] or None


def add_file(
    rec: Records,
    name: str,
    data: bytes,
    *,
    actor: str,
    embedder: search.Embedder | None = None,
    flags: Sequence[Flag] = (),
    folder: str | None = None,
    note: str | None = None,
) -> FileInfo:
    """Raises `RecordsError`: FILE_EMPTY (422) or FILE_TOO_BIG (413), and then nothing is stored.

    `name` and `folder` are display text only and never touch the disk. `flags` are hidden-text
    flags the caller found and the stored bytes no longer show (a web page's hidden elements),
    kept with the file's own; they are not added again when the same bytes are already stored.
    `note` (a `copy` name) replaces what reading the file noted: a zip kept and not opened."""
    name = re.split(r"[/\\]", name)[-1][:255]
    folder = clean_folder(folder)
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
    all_flags = [*extracted.flags, *flags]
    file_id = uuid.uuid4().hex
    with rec.write(actor) as conn:
        found = _same_bytes(conn, sha256)  # the same bytes may have come in meanwhile
        if found is not None:
            return found
        from qsone.records.mapping import store as map_store

        at = rec.clock()
        conn.executemany(
            "INSERT INTO file_pieces(sha256, seq, data) VALUES (?, ?, ?)",
            (
                (sha256, seq, data[start : start + PIECE_BYTES])
                for seq, start in enumerate(range(0, len(data), PIECE_BYTES))
            ),
        )
        old = conn.execute(
            "SELECT id FROM files WHERE name = ? AND folder IS ? AND valid_until IS NULL",
            (name, folder),
        ).fetchone()
        replaces = None if old is None else old[0]
        if replaces is not None:
            map_store.expire(conn, rec, replaces, at, actor=actor)
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
            "note": note or extracted.note,
            "pages": extracted.pages,
            "added_at": at,
            "added_by": actor,
            "replaces": replaces,
            "folder": folder,
        }
        conn.execute(
            "INSERT INTO files(id, name, kind, size, sha256, status, note, pages, added_at,"
            " added_by, replaces, folder) VALUES (:id, :name, :kind, :size, :sha256, :status,"
            " :note, :pages, :added_at, :added_by, :replaces, :folder)",
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
        map_store.enqueue(conn, rec, file_id, extracted.kind, extracted.pages, actor=actor)
        if extracted.kind == "pdf":
            _extraction_meta(rec, conn, file_id, extracted)
        indexed = []
        for seq, piece in enumerate(chunks):
            cur = conn.execute(
                "INSERT INTO chunks(file_id, seq, locator, text) VALUES (?, ?, ?, ?)",
                (file_id, seq, json.dumps(piece.locator, ensure_ascii=False), piece.text),
            )
            indexed.append((cur.lastrowid, piece.text))
        search.index_words(conn, indexed)
        conn.executemany(
            "INSERT INTO file_flags(file_id, kind, locator, excerpt, count) VALUES (?, ?, ?, ?, ?)",
            (
                (file_id, f.kind, json.dumps(f.locator, ensure_ascii=False), f.excerpt, f.count)
                for f in all_flags
            ),
        )
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
        row["note"],
        extracted.pages,
        len(chunks),
        at,
        replaces,
        None,
        len(all_flags),
        folder,
        ",".join(sorted({f.kind for f in all_flags})) or None,
    )


def file_info(rec: Records, file_id: str) -> FileInfo | None:
    """One file, current or old; None for an unknown id."""
    with rec.read() as conn:
        row = conn.execute(f"{_INFO} WHERE f.id = ?", (file_id,)).fetchone()
    return None if row is None else FileInfo(*row)


def list_flags(rec: Records, file_id: str) -> list[dict] | None:
    """A file's hidden-text flags in the order they were found: kind, locator, excerpt (at most
    160 characters) and count. None for an unknown id."""
    with rec.read() as conn:
        if conn.execute("SELECT 1 FROM files WHERE id = ?", (file_id,)).fetchone() is None:
            return None
        rows = conn.execute(
            "SELECT kind, locator, excerpt, count FROM file_flags WHERE file_id = ? ORDER BY id",
            (file_id,),
        ).fetchall()
    return [
        {"kind": kind, "locator": json.loads(locator), "excerpt": excerpt, "count": count}
        for kind, locator, excerpt, count in rows
    ]


def read_pages(conn, file_id: str) -> set[int]:
    """The pages of a file that have text: a text layer, or read from the page image."""
    rows = conn.execute(
        "SELECT DISTINCT json_extract(locator, '$.page') FROM chunks"
        " WHERE file_id = ? AND json_extract(locator, '$.page') IS NOT NULL",
        (file_id,),
    )
    return {int(page) for (page,) in rows}


def _extraction_meta(rec, conn, file_id, extracted):
    rec.set_meta(conn, "extractor:" + file_id, str(EXTRACTOR_VERSION))
    rec.set_meta(conn, "pdf_sources:" + file_id, json.dumps(extracted.page_sources))


def reread_pdf(rec):
    """One old PDF per background slice, using only its encrypted in-database original.

    Replaces derived native text and its indexes; OCR words and source page locators
    survive. Version and text commit atomically, so restart cannot skip an old file.
    """
    from qsone.records.mapping import store

    with rec.read() as c:
        pending = c.execute(
            "SELECT f.id,f.name FROM files f LEFT JOIN meta m ON m.key='extractor:'||f.id "
            "WHERE f.kind='pdf' AND f.valid_until IS NULL AND coalesce(m.value,'')<>? "
            "ORDER BY f.id LIMIT 1",
            (str(EXTRACTOR_VERSION),),
        ).fetchone()
    if pending is None:
        return False
    file_id, name = pending
    result = extract(name, read_original(rec, file_id))
    with rec.write(store.ACTOR) as c:
        if c.execute("SELECT valid_until FROM files WHERE id=?", (file_id,)).fetchone()[0]:
            return True
        old = c.execute(
            "SELECT id FROM chunks WHERE file_id=? AND json_extract(locator,'$.read_by') IS NULL",
            (file_id,),
        ).fetchall()
        vectors = c.execute("SELECT 1 FROM sqlite_master WHERE name='chunk_vectors'").fetchone()
        for (chunk_id,) in old:
            c.execute("DELETE FROM chunks_fts WHERE rowid=?", (chunk_id,))
            if vectors:
                c.execute("DELETE FROM chunk_vectors WHERE chunk_id=?", (chunk_id,))
            c.execute("DELETE FROM chunks WHERE id=?", (chunk_id,))
        seq = c.execute(
            "SELECT coalesce(max(seq),-1)+1 FROM chunks WHERE file_id=?", (file_id,)
        ).fetchone()[0]
        indexed = []
        for piece in chunk(result.pieces):
            cur = c.execute(
                "INSERT INTO chunks(file_id,seq,locator,text) VALUES (?,?,?,?)",
                (file_id, seq, json.dumps(piece.locator), piece.text),
            )
            indexed.append((cur.lastrowid, piece.text))
            seq += 1
        search.index_words(c, indexed)
        _extraction_meta(rec, c, file_id, result)
        # Retire facts grounded in the old reading, then remap only this file.
        store.expire(c, rec, file_id, rec.clock())
        store.write(
            c,
            rec,
            "map_files",
            dict(
                file_id=file_id,
                # a project made before the map has no map row yet: kind and pages create it
                kind="pdf",
                pages=result.pages,
                valid_until=None,
                local_state="waiting",
                ai_state=None,
                ai_attempts=0,
                structure={},
                key_pages=[],
                note=None,
            ),
        )
        audit.record(
            c,
            at=rec.clock(),
            actor=store.ACTOR,
            action="reread",
            table="files",
            row_id=file_id,
            before=None,
            after={"extractor_version": EXTRACTOR_VERSION, "page_sources": result.page_sources},
        )
    return True


def add_ocr_pages(
    rec: Records,
    file_id: str,
    pages: dict[int, str | list[Piece]],
    *,
    read_by: str,
    actor: str,
    include_text_pages: bool = False,
) -> int:
    """Stores OCR page text or word Pieces (a scanned PDF, or an image as page 1).
    Local OCR Pieces retain boxes and confidence; AI text is chunked as before. Keeps
    chunks with the locator {"page": n, "read_by": <model id>}, the word index,
    flags for lines that look like orders to an AI, the file's status, and one audit row. A
    page that already has text is left as it is (unless include_text_pages appends
    local OCR to a sparse text layer); a page read as empty is kept as read. Vectors
    come from Plan 2b's worker, which embeds every chunk that has none. Returns how many pages
    were stored. Raises `RecordsError`: FILE_NOT_IN_PROJECT, or FILE_PAGES_OUT_OF_RANGE
    (field "pages")."""
    with rec.write(actor) as conn:
        row = conn.execute(
            "SELECT pages, status, note FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if row is None:
            raise RecordsError(copy.FILE_NOT_IN_PROJECT, status=422, field="file_id")
        count, status, note = row
        if count is None or any(not 1 <= n <= count for n in pages):
            text = copy.fill(copy.FILE_PAGES_OUT_OF_RANGE, pages=str(count or 0))
            raise RecordsError(text, status=422, field="pages")
        done = read_pages(conn, file_id)
        already = done
        if include_text_pages:
            # Sparse text layers can still be scanned pages. Append OCR words while
            # retaining original text and never duplicating a completed OCR page.
            already = {
                int(n)
                for (n,) in conn.execute(
                    "SELECT DISTINCT json_extract(locator, '$.page') FROM chunks "
                    "WHERE file_id=? AND json_extract(locator, '$.read_by') IS NOT NULL",
                    (file_id,),
                )
            }
        new = {n: t for n, t in sorted(pages.items()) if n not in already}
        if not new:
            return 0
        (seq,) = conn.execute(
            "SELECT coalesce(max(seq), -1) + 1 FROM chunks WHERE file_id = ?", (file_id,)
        ).fetchone()
        pieces = []
        for n, text in new.items():
            locator = {"page": n, "read_by": read_by}
            # an empty page is kept as one empty chunk, so it counts as read
            if isinstance(text, list):
                # OCR words remain individual records: never merge their source boxes.
                pieces += [Piece(p.locator | locator, display_text(p.text)) for p in text]
            else:
                pieces += chunk([Piece(locator, display_text(text))]) or [Piece(locator, "")]
        # Scan whole OCR page phrases for injection, even though words stay separate.
        flag_pieces = []
        for n, text in new.items():
            page_text = " ".join(p.text for p in text) if isinstance(text, list) else text
            flag_pieces.append(Piece({"page": n, "read_by": read_by}, page_text))
        indexed = []
        for piece in pieces:
            cur = conn.execute(
                "INSERT INTO chunks(file_id, seq, locator, text) VALUES (?, ?, ?, ?)",
                (file_id, seq, json.dumps(piece.locator, ensure_ascii=False), piece.text),
            )
            indexed.append((cur.lastrowid, piece.text))
            seq += 1
        search.index_words(conn, indexed)
        conn.executemany(
            "INSERT INTO file_flags(file_id, kind, locator, excerpt, count) VALUES (?, ?, ?, ?, ?)",
            (
                (file_id, f.kind, json.dumps(f.locator, ensure_ascii=False), f.excerpt, f.count)
                for f in hidden.ai_instruction_flags([p for p in flag_pieces if p.text])
            ),
        )
        complete = len(done | set(new)) >= count
        after = {"status": "read" if complete else "partly_read"}
        after["note"] = None if complete else "FILE_SCANNED_PAGES"
        conn.execute(
            "UPDATE files SET status = ?, note = ? WHERE id = ?",
            (after["status"], after["note"], file_id),
        )
        audit.record(
            conn,
            at=rec.clock(),
            actor=actor,
            action="read_pages",
            table="files",
            row_id=file_id,
            before={"status": status, "note": note},
            after=after | {"pages": list(new), "read_by": read_by},
        )
    return len(new)


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
