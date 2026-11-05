"""The Web Log (Plan 5, decision 10): one row for every search and every page read, never edited
or deleted, in the project's Records (or Engineer Records for the General chat). A page read
points at its snapshot file, so the Checking QS opens exactly what was read."""

import json
import uuid
from dataclasses import asdict

from qsone.records.project import Records
from qsone.web.search import SearchHit

_COLUMNS = (
    "id, at, actor, brief_id, action, provider, query, url, final_url, status, title, dated,"
    " dated_how, file_id, results"
)


def _row(row) -> dict:
    found = dict(zip(_COLUMNS.split(", "), row, strict=True))
    found["results"] = None if found["results"] is None else json.loads(found["results"])
    return found


def add_search(
    rec: Records,
    *,
    at: str,
    actor: str,
    brief_id: str | None,
    provider: str,
    query: str,
    hits: list[SearchHit],
) -> str:
    log_id = uuid.uuid4().hex
    with rec.write(actor) as conn:
        conn.execute(
            "INSERT INTO web_log(id, at, actor, brief_id, action, provider, query, results)"
            " VALUES (?, ?, ?, ?, 'search', ?, ?, ?)",
            (
                log_id,
                at,
                actor,
                brief_id,
                provider,
                query,
                json.dumps([asdict(h) for h in hits], ensure_ascii=False),
            ),
        )
    return log_id


def add_read(
    rec: Records,
    *,
    at: str,
    actor: str,
    brief_id: str | None,
    url: str,
    final_url: str,
    status: int,
    title: str,
    dated: str | None,
    dated_how: str | None,
    file_id: str,
) -> str:
    log_id = uuid.uuid4().hex
    with rec.write(actor) as conn:
        conn.execute(
            "INSERT INTO web_log(id, at, actor, brief_id, action, url, final_url, status, title,"
            " dated, dated_how, file_id) VALUES (?, ?, ?, ?, 'read', ?, ?, ?, ?, ?, ?, ?)",
            (log_id, at, actor, brief_id, url, final_url, status, title, dated, dated_how, file_id),
        )
    return log_id


def get(rec: Records, log_id: str) -> dict | None:
    with rec.read() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM web_log WHERE id = ?", (log_id,)).fetchone()
    return None if row is None else _row(row)


def latest(rec: Records) -> dict | None:
    """The newest row, or None."""
    with rec.read() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM web_log ORDER BY rowid DESC LIMIT 1").fetchone()
    return None if row is None else _row(row)


def last_read(rec: Records, *, brief_id: str, url: str) -> dict | None:
    """This Brief's newest read of `url`, or None."""
    with rec.read() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM web_log WHERE action = 'read' AND brief_id = ? AND url = ?"
            " ORDER BY rowid DESC LIMIT 1",
            (brief_id, url),
        ).fetchone()
    return None if row is None else _row(row)
