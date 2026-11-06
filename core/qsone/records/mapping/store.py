"""Audited map writes and bounded, indexed reads. Locators use ONE's source frame."""

import base64
import json
import uuid

from qsone import copy
from qsone.records import audit

ACTOR = "one"
JSON_FIELDS = {
    "group_labels",
    "scanned_pages",
    "ocr_done_pages",
    "structure",
    "key_pages",
    "ai_title",
    "note",
    "locator",
    "header",
    "column_guess",
    "counts",
    "rooms",
    "source",
    "from_locator",
    "to_locator",
    "words",
    "evidence",
    "box",
    "picture_check",
    "conflict_with",
}
TABLES = {"map_files", "map_tables", "map_sheets", "map_links", "map_facts"}


def rows(conn, sql, args=()):
    cur = conn.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur]


def decoded(row):
    result = {
        k: json.loads(v)
        if (k in JSON_FIELDS or (k == "name" and "conflict_with" in row)) and v is not None
        else v
        for k, v in row.items()
    }
    if "conflict_with" in row:
        from qsone.records.mapping.facts import shown

        return shown(result)
    return result


def write(conn, rec, table, row, *, actor=ACTOR):
    """Write and audit together. Later map jobs use this for facts, links and sheets too."""
    if table not in TABLES:
        raise ValueError(table)
    key = "file_id" if table == "map_files" else "id"
    row = dict(row)
    row.setdefault(key, uuid.uuid4().hex)
    before = rows(conn, f"SELECT * FROM {table} WHERE {key}=?", (row[key],))
    encoded = {
        k: json.dumps(v, ensure_ascii=False)
        if (k in JSON_FIELDS or (k == "name" and table == "map_facts")) and v is not None
        else v
        for k, v in row.items()
    }
    if before:
        fields = [k for k in encoded if k != key]
        conn.execute(
            f"UPDATE {table} SET " + ",".join(f'"{k}"=?' for k in fields) + f" WHERE {key}=?",
            (*[encoded[k] for k in fields], row[key]),
        )
    else:
        conn.execute(
            f"INSERT INTO {table} ("
            + ",".join(f'"{k}"' for k in encoded)
            + ") VALUES ("
            + ",".join("?" for _ in encoded)
            + ")",
            tuple(encoded.values()),
        )
    audit.record(
        conn,
        at=rec.clock(),
        actor=actor,
        action="update" if before else "create",
        table=table,
        row_id=("map:" + row[key]) if table == "map_files" else row[key],
        before=decoded(before[0]) if before else None,
        after=row,
    )


def expire(conn, rec, file_id, at, *, actor=ACTOR):
    for table in TABLES:
        where = "from_file_id=? OR to_file_id=?" if table == "map_links" else "file_id=?"
        args = (file_id, file_id) if table == "map_links" else (file_id,)
        for row in rows(
            conn, f"SELECT * FROM {table} WHERE ({where}) AND valid_until IS NULL", args
        ):
            key = "file_id" if table == "map_files" else "id"
            write(conn, rec, table, {key: row[key], "valid_until": at}, actor=actor)


def enqueue(conn, rec, file_id, kind, pages, *, actor=ACTOR):
    write(conn, rec, "map_files", {"file_id": file_id, "kind": kind, "pages": pages}, actor=actor)


def seed(rec, limit=100):
    """Bounded backfill for projects made before the map migration."""
    with rec.write(ACTOR) as conn:
        missing = conn.execute(
            "SELECT f.id,f.kind,f.pages FROM files f LEFT JOIN map_files m "
            "ON m.file_id=f.id WHERE f.valid_until IS NULL AND m.file_id IS NULL "
            "ORDER BY f.id LIMIT ?",
            (limit,),
        ).fetchall()
        for file_id, kind, pages in missing:
            enqueue(conn, rec, file_id, kind, pages)
    return len(missing)


def list_map(rec, *, parent=None, cursor=None, limit=100):
    limit = max(1, min(limit, 200))
    fcursor, gcursor = "", ""
    if cursor:
        try:
            fcursor, gcursor = json.loads(base64.urlsafe_b64decode(cursor).decode())
        except (ValueError, TypeError, UnicodeError):
            from qsone.records.project import RecordsError

            raise RecordsError(copy.MAP_CURSOR_INVALID, status=422) from None
    group = (
        "coalesce(m.ai_group, CASE WHEN coalesce(f.folder,'')='' THEN f.kind "
        "ELSE f.folder||'/'||f.kind END)"
    )
    with rec.read() as c:
        counts = dict(
            c.execute(
                "SELECT coalesce(m.local_state,'waiting'),count(*) FROM files f "
                "LEFT JOIN map_files m ON m.file_id=f.id WHERE f.valid_until IS NULL "
                "GROUP BY coalesce(m.local_state,'waiting')"
            ).fetchall()
        )
        status = {k: counts.get(k, 0) for k in ("waiting", "reading", "done", "failed")}
        status["total"] = sum(status.values())
        status["line"] = copy.fill(
            copy.MAP_PROGRESS,
            done=f"{status['done'] + status['failed']:,}",
            total=f"{status['total']:,}",
        )
        ai_failed = c.execute(
            "SELECT count(*) FROM map_files WHERE valid_until IS NULL AND ai_state='failed'"
        ).fetchone()[0]
        status["ai_failed"] = ai_failed
        if ai_failed:
            reason = c.execute(
                "SELECT note FROM map_files WHERE valid_until IS NULL "
                "AND ai_state='failed' ORDER BY file_id LIMIT 1"
            ).fetchone()[0]
            status["line"] = copy.fill(
                copy.MAP_AI_FAILED,
                count=str(ai_failed),
                reason=json.loads(reason) if reason else copy.MAP_AI_FAILED_REASON,
            )
        status["passes"] = _pass_summary(c)
        pass_failed = False
        for name, outcome in status["passes"].items():
            if outcome["state"] != "failed":
                continue
            line = copy.fill(
                copy.MAP_PASS_FAILED,
                stage=copy.MAP_PASS_FACTS if name == "facts" else copy.MAP_PASS_LINKS,
                reason=outcome["note"],
            )
            if ai_failed or pass_failed:
                status["line"] = {
                    lang: status["line"][lang] + " " + line[lang] for lang in ("en", "ar")
                }
            else:
                status["line"] = line
            pass_failed = True
        # Return immediate child groups, bounded and keyset-paged alongside the files.
        prefix = (parent.rstrip("/") + "/") if parent else ""
        groups = rows(
            c,
            f"SELECT path,count(*) AS count FROM (SELECT CASE WHEN instr(rest,'/')>0 "
            "THEN substr(rest,1,instr(rest,'/')-1) ELSE rest END AS path FROM "
            f"(SELECT substr({group},length(?)+1) AS rest FROM files f LEFT JOIN map_files m "
            f"ON m.file_id=f.id WHERE f.valid_until IS NULL AND substr({group},1,length(?))=?)) "
            "WHERE path<>'' AND path>? GROUP BY path ORDER BY path LIMIT ?",
            (prefix, prefix, prefix, gcursor, limit + 1),
        )
        result = rows(
            c,
            "SELECT f.id AS file_id,f.name,f.folder,f.kind,f.pages,"
            "coalesce(m.read_how,'stored') AS read_how,m.ai_title,m.ai_group,"
            "coalesce(m.key_pages,'[]') AS key_pages,m.ai_state,m.note,"
            "coalesce(m.local_state,'waiting') AS local_state "
            "FROM files f LEFT JOIN map_files m ON m.file_id=f.id "
            f"WHERE f.valid_until IS NULL AND f.id>? AND (? IS NULL OR {group}=?) "
            "ORDER BY f.id LIMIT ?",
            (fcursor, parent, parent, limit + 1),
        )
    return {
        "status": status,
        "groups": [
            {
                "path": prefix + g["path"],
                "label": _group_label(rec, prefix + g["path"], g["path"]),
                "count": g["count"],
            }
            for g in groups[:limit]
        ],
        "files": [decoded(r) for r in result[:limit]],
        "next_cursor": base64.urlsafe_b64encode(
            json.dumps(
                [
                    result[min(len(result), limit) - 1]["file_id"] if result else fcursor,
                    groups[min(len(groups), limit) - 1]["path"] if groups else gcursor,
                ]
            ).encode()
        ).decode()
        if len(result) > limit or len(groups) > limit
        else None,
    }


def detail(rec, file_id):
    with rec.read() as c:
        found = rows(c, "SELECT * FROM map_files WHERE file_id=?", (file_id,))
        if not found:
            return None
        out = decoded(found[0])
        for name in ("tables", "sheets", "facts", "links"):
            where = "from_file_id=? OR to_file_id=?" if name == "links" else "file_id=?"
            args = (file_id, file_id) if name == "links" else (file_id,)
            out[name] = [
                decoded(r)
                for r in rows(
                    c,
                    f"SELECT * FROM map_{name} WHERE ({where}) AND valid_until IS ?",
                    (*args, out["valid_until"]),
                )
            ]
    from collections import Counter

    counts = Counter()
    for sheet in out["sheets"]:
        counts.update(sheet["counts"])
    out["file_counts"] = dict(counts)
    out["file_counts_source"] = {"file_id": file_id}
    if any(sheet["sheet"] != "Model" for sheet in out["sheets"]):
        out["sheets"] = [sheet for sheet in out["sheets"] if sheet["sheet"] != "Model"]
    out["sheets"].sort(key=lambda sheet: (sheet["number"] or "", sheet["sheet"]))
    return out


def entries(rec, name, *, cursor=None, limit=100, file_id=None):
    assert name in ("facts", "links")
    limit = max(1, min(limit, 200))
    filter_ = ""
    args = [cursor or ""]
    if file_id is not None:
        filter_ = " AND (from_file_id=? OR to_file_id=?)" if name == "links" else " AND file_id=?"
        args.extend([file_id, file_id] if name == "links" else [file_id])
    with rec.read() as c:
        found = rows(
            c,
            f"SELECT * FROM map_{name} WHERE valid_until IS NULL AND id>?{filter_} "
            "ORDER BY id LIMIT ?",
            (*args, limit + 1),
        )
    return {
        name: [decoded(r) for r in found[:limit]],
        "next_cursor": found[limit - 1]["id"] if len(found) > limit else None,
    }


def _group_label(rec, path, fallback):
    with rec.read() as c:
        row = c.execute(
            "SELECT json_extract(group_labels, ?) FROM map_files "
            "WHERE valid_until IS NULL AND json_extract(group_labels, ?) IS NOT NULL LIMIT 1",
            ("$." + json.dumps(path), "$." + json.dumps(path)),
        ).fetchone()
    return json.loads(row[0]) if row else {"en": fallback, "ar": fallback}


def pass_status(rec, name, file_ids, *, state, attempts, note=None):
    """Persist project-pass outcomes independently of per-file classification state."""
    key = "project_map_passes"
    batch = "project" if name == "facts" else ",".join(sorted(file_ids))
    with rec.write(ACTOR) as c:
        raw = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        before = json.loads(raw[0]) if raw else {}
        after = {stage: dict(runs) for stage, runs in before.items()}
        after.setdefault(name, {})[batch] = {
            "state": state,
            "attempts": attempts,
            "note": note,
            "at": rec.clock(),
        }
        rec.set_meta(c, key, json.dumps(after, ensure_ascii=False))
        audit.record(
            c,
            at=rec.clock(),
            actor=ACTOR,
            action="update" if raw else "create",
            table="meta",
            row_id=key,
            before=before,
            after=after,
        )


def _pass_summary(c):
    raw = c.execute("SELECT value FROM meta WHERE key='project_map_passes'").fetchone()
    result = {}
    for name, runs in (json.loads(raw[0]) if raw else {}).items():
        records = list(runs.values())
        failed = [r for r in records if r["state"] == "failed"]
        pending = [r for r in records if r["state"] in ("running", "retrying")]
        latest = max(pending or failed or records, key=lambda r: r["at"])
        result[name] = {
            "state": latest["state"],
            "note": latest["note"],
            "attempts": max(r["attempts"] for r in records),
            "failed_batches": len(failed),
        }
    counts = c.execute("SELECT value FROM meta WHERE key='project_map_fact_counts'").fetchone()
    if counts:
        result.setdefault(
            "facts", {"state": "done", "note": None, "attempts": 1, "failed_batches": 0}
        )["counts"] = json.loads(counts[0])
    return result


def retain_rejected(rec, proposals):
    """Keep private proposals in the encrypted project DB, never application logs."""
    import hashlib

    with rec.write(ACTOR) as c:
        for proposal, reason in proposals:
            raw = json.dumps(proposal, ensure_ascii=False, sort_keys=True)
            key = hashlib.sha256((reason + raw).encode()).hexdigest()
            c.execute(
                "INSERT OR IGNORE INTO map_rejected_facts (id,proposal,reason,recorded_at) "
                "VALUES (?,?,?,?)",
                (key, raw, reason, rec.clock()),
            )


def rejected_entries(rec, *, cursor=None, limit=100):
    limit = max(1, min(limit, 200))
    with rec.read() as c:
        found = rows(
            c,
            "SELECT * FROM map_rejected_facts WHERE id>? ORDER BY id LIMIT ?",
            (cursor or "", limit + 1),
        )
    return {
        "rejected": [
            dict(r, proposal=json.loads(r["proposal"]), verification=copy.MAP_FACT_REJECTED)
            for r in found[:limit]
        ],
        "next_cursor": found[limit - 1]["id"] if len(found) > limit else None,
    }
