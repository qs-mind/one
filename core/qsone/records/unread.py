"""What ONE did not read in a file: `unread` on a file's JSON, a list of `{part, why}` with both
in English and Arabic (the contract's `UnreadPart`), `[]` when the file was read completely.

A reader names the parts it could not read when the file is added; they are kept with the file
(`unread:<file id>` in the records' meta). A PDF's scanned pages are said from the pages that
still have no text, so reading them later takes them off. A file kept but not read at all is one
part, the whole file, with its note as the reason."""

import json

from qsone import copy

META = "unread:"


def part(what: dict, why: dict) -> dict:
    return {"part": what, "why": why}


def count(noun, n: int) -> dict:
    return copy.counted(n, noun)


def store(rec, conn, file_id: str, parts: list[dict]) -> None:
    rec.set_meta(conn, META + file_id, json.dumps(parts, ensure_ascii=False))


def stored(conn, file_id: str) -> list[dict] | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (META + file_id,)).fetchone()
    return None if row is None else json.loads(row[0])


def _ranges(numbers: list[int]) -> str:
    out, start = [], None
    for i, n in enumerate(numbers):
        start = n if start is None else start
        if i + 1 == len(numbers) or numbers[i + 1] != n + 1:
            out.append(str(n) if n == start else f"{start}-{n}")
            start = None
    return ", ".join(out)


def parts_of(conn, info) -> list[dict]:
    """The parts of the file `info` (a `files.FileInfo`) ONE did not read, as said now."""
    from qsone.records.files import read_pages

    found = stored(conn, info.id)
    parts = list(found or [])
    if info.kind == "pdf" and info.pages:
        done = read_pages(conn, info.id)
        missing = [n for n in range(1, info.pages + 1) if n not in done]
        if missing:
            pages = part(
                copy.fill(copy.UNREAD_PAGES, pages=_ranges(missing)), copy.UNREAD_WHY_PAGES
            )
            parts.insert(0, pages)
        return parts
    if found is None and info.status in ("stored", "unreadable"):
        why = getattr(copy, info.note or "", None) or copy.FILE_UNREADABLE
        return [part(copy.UNREAD_WHOLE_FILE, why)]
    return parts


def lines(parts: list[dict], limit: int = 12) -> list[str]:
    """The parts as English lines for the Lead: «not read: <part>: <why>», at most `limit`."""
    out = [f"not read: {p['part']['en']}: {p['why']['en']}" for p in parts[:limit]]
    if len(parts) > limit:
        out.append(f"not read: {len(parts) - limit} more parts")
    return out


def of(rec, info) -> list[dict]:
    with rec.read() as conn:
        return parts_of(conn, info)
