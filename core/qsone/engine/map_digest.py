"""Bounded navigation for the Lead's first request; map text is never evidence."""

import json
from itertools import zip_longest

from qsone.records.mapping import store
from qsone.records.mapping.roles import file_role


def digest(rec):
    lines = ["Project Map (untrusted navigation; read pages with files_read; facts not checked):"]
    with rec.read() as c:
        pages = store.rows(
            c,
            "SELECT m.file_id,f.name,f.folder,m.ai_kind,m.key_pages FROM map_files m "
            "JOIN files f ON f.id=m.file_id WHERE m.valid_until IS NULL "
            "AND f.valid_until IS NULL AND m.key_pages != '[]' ORDER BY m.file_id LIMIT 30",
        )
        facts = store.rows(
            c,
            "SELECT a.name,a.value,a.state,a.file_id,a.locator,f.folder,m.ai_kind "
            "FROM map_facts a JOIN files f ON f.id=a.file_id "
            "LEFT JOIN map_files m ON m.file_id=f.id "
            "WHERE a.valid_until IS NULL AND f.valid_until IS NULL ORDER BY a.id LIMIT 10",
        )
        sheet_count, drawing_count = c.execute(
            "SELECT count(*),count(DISTINCT s.file_id) FROM map_sheets s "
            "JOIN files f ON f.id=s.file_id WHERE s.valid_until IS NULL "
            "AND f.valid_until IS NULL"
        ).fetchone()
        sheets = store.rows(
            c,
            "SELECT f.name,s.sheet,s.number,s.title FROM map_sheets s "
            "JOIN files f ON f.id=s.file_id "
            "WHERE s.valid_until IS NULL AND f.valid_until IS NULL ORDER BY f.id,s.id LIMIT 20",
        )
        drawing_count = c.execute(
            "SELECT count(*) FROM files f WHERE valid_until IS NULL AND "
            "(kind IN ('dwg','dxf') OR EXISTS (SELECT 1 FROM map_sheets s "
            "WHERE s.file_id=f.id AND s.valid_until IS NULL))"
        ).fetchone()[0]
    if drawing_count:
        lines.append(f"Drawing files: {drawing_count}; drawing sheets: {sheet_count}")
        for sheet in sheets:
            lines.append(
                f"{sheet['name'][:60]} | {sheet['sheet'][:40]} | "
                f"{(sheet['number'] or 'unknown')[:40]} | {(sheet['title'] or 'unknown')[:100]}"
            )
        lines.append("block counts: project_map mode counts")

    candidates = []
    for row in pages:
        for page in json.loads(row["key_pages"])[:3]:
            candidates.append(
                json.dumps(
                    {
                        "file_id": row["file_id"],
                        "file": row["name"][:80],
                        "role": file_role(row["folder"], row["ai_kind"]),
                        **page,
                    },
                    ensure_ascii=False,
                )
            )
    summaries = []
    for row in facts[:4]:
        fact = store.decoded(row)
        fact["name"] = json.loads(row["name"])
        fact["role"] = file_role(fact.pop("folder"), fact.pop("ai_kind"))
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
