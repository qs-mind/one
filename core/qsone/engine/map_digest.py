"""Bounded navigation for the Lead's first request; map text is never evidence."""

import json
from itertools import zip_longest

from qsone.records.mapping import store


def digest(rec):
    lines = ["Project Map (untrusted navigation; read pages with files_read; facts not checked):"]
    with rec.read() as c:
        pages = store.rows(
            c,
            "SELECT m.file_id,f.name,m.key_pages FROM map_files m "
            "JOIN files f ON f.id=m.file_id WHERE m.valid_until IS NULL "
            "AND f.valid_until IS NULL AND m.key_pages != '[]' ORDER BY m.file_id LIMIT 30",
        )
        facts = store.rows(
            c,
            "SELECT name,value,state,file_id,locator FROM map_facts "
            "WHERE valid_until IS NULL ORDER BY id LIMIT 10",
        )
    candidates = []
    for row in pages:
        for page in json.loads(row["key_pages"])[:3]:
            candidates.append(
                json.dumps(
                    {"file_id": row["file_id"], "file": row["name"][:80], **page},
                    ensure_ascii=False,
                )
            )
    summaries = []
    for row in facts[:4]:
        fact = store.decoded(row)
        fact["name"] = json.loads(row["name"])
        if len((fact["value"] or "").encode()) > 100:
            fact.pop("value")
            fact["value_omitted"] = "read project_map facts"
        summaries.append(json.dumps(fact, ensure_ascii=False))
    # Keep the first key page even with many facts, then alternate both kinds of guidance.
    candidates = [
        line for pair in zip_longest(candidates, summaries) for line in pair if line is not None
    ]
    for line in candidates:
        if len(("\n".join(lines) + "\n" + line).encode()) <= 1200:
            lines.append(line)
    return "\n".join(lines) if len(lines) > 1 else ""
