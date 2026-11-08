"""Project names: folder defaults, sourced tender names, and protected engineer edits."""

import json

from qsone.records import audit


def rename(rec, name, *, actor, source=None, conn=None):
    def write(c):
        meta = dict(c.execute("SELECT key,value FROM meta"))
        if actor != "engineer" and meta.get("name_origin", "engineer") == "engineer":
            return False
        after = {
            "name": name,
            "name_origin": "engineer" if actor == "engineer" else "tender",
            "name_source": json.dumps(source, ensure_ascii=False),
        }
        if all(meta.get(k) == v for k, v in after.items()):
            return False
        for k, v in after.items():
            rec.set_meta(c, k, v)
        rec.set_meta(c, "name_pair", "{}")
        audit.record(
            c,
            at=rec.clock(),
            actor=actor,
            action="update",
            table="meta",
            row_id="name",
            before={k: meta.get(k) for k in after},
            after=after,
        )
        return True

    if conn is not None:
        return write(conn)
    with rec.write(actor) as c:
        return write(c)


def from_facts(c, rec):
    from qsone.records.mapping import store

    origin = c.execute("SELECT value FROM meta WHERE key='name_origin'").fetchone()
    if origin is None or origin[0] == "engineer":
        return False
    rows = [
        store.decoded(r)
        for r in store.rows(
            c, "SELECT * FROM map_facts WHERE valid_until IS NULL AND state='found'"
        )
    ]
    names = [
        r
        for r in rows
        if r["name"]["en"].strip().casefold()
        in {"project name", "official project name", "name of project", "tender name"}
    ]
    if not names or len({r["corrected_value"] or r["value"] for r in names}) != 1:
        return
    row = names[0]
    value = (row["corrected_value"] or row["value"]).strip()
    if not value or len(value) > 200 or not row["locator"].get("page"):
        return
    file = c.execute(
        "SELECT name FROM files WHERE id=? AND valid_until IS NULL", (row["file_id"],)
    ).fetchone()
    if file:
        return rename(
            rec,
            value,
            actor="engineer" if row["corrected_value"] is not None else store.ACTOR,
            conn=c,
            source={
                "fact_id": row["id"],
                "file_id": row["file_id"],
                "file": file[0],
                "locator": row["locator"],
                "box": row["box"],
            },
        )
