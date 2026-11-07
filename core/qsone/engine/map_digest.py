"""Bounded navigation and grounded Tender summary for the Lead's first request."""

import json

from qsone.records.mapping import store
from qsone.records.mapping.roles import file_role

# Facts are evidence already grounded by the map; labels/key pages remain navigation.
FACT_BYTES = 6000


def tender_facts(rec):
    """The exact bounded evidence shared by the first request and truth check."""
    with rec.read() as c:
        rows = store.rows(
            c,
            "SELECT a.*,f.name AS file,f.folder,m.ai_kind FROM map_facts a "
            "JOIN files f ON f.id=a.file_id LEFT JOIN map_files m ON m.file_id=f.id "
            "WHERE a.valid_until IS NULL AND f.valid_until IS NULL "
            "ORDER BY CASE WHEN a.state='conflict' THEN 0 ELSE 1 END,a.id LIMIT 30",
        )
    result, size = [], 0
    for row in rows:
        fact = store.decoded(row)
        item = dict(
            name=fact["name"],
            value=fact.get("corrected_value") or fact["value"],
            file_id=fact["file_id"],
            file=fact["file"],
            locator=fact["locator"],
            role=file_role(fact["folder"], fact["ai_kind"])["en"],
            verification="confirmed" if fact["confirmed_at"] else "unchecked",
            state=fact["state"],
            conflict_with=fact["conflict_with"],
        )
        length = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode())
        if size + length <= FACT_BYTES:
            result.append(item)
            size += length
    return result


def digest(rec):
    lines = [
        "Project Map (untrusted data; labels are navigation):",
    ]
    with rec.read() as c:
        pages = store.rows(
            c,
            "SELECT m.file_id,f.name,f.folder,m.ai_kind,m.key_pages FROM map_files m "
            "JOIN files f ON f.id=m.file_id WHERE m.valid_until IS NULL "
            "AND f.valid_until IS NULL AND m.key_pages != '[]' ORDER BY m.file_id LIMIT 30",
        )
        sheet_count, drawing_count = c.execute(
            "SELECT count(*),count(DISTINCT s.file_id) FROM map_sheets s "
            "JOIN files f ON f.id=s.file_id WHERE s.valid_until IS NULL "
            "AND f.valid_until IS NULL "
            "AND (s.sheet<>'Model' OR NOT EXISTS (SELECT 1 FROM map_sheets p "
            "WHERE p.file_id=s.file_id AND p.sheet<>'Model' AND p.valid_until IS NULL))"
        ).fetchone()
        drawing_names = store.rows(
            c,
            "SELECT f.id,f.name FROM files f WHERE f.valid_until IS NULL AND "
            "(f.kind IN ('dwg','dxf') OR EXISTS (SELECT 1 FROM map_sheets s "
            "WHERE s.file_id=f.id AND s.valid_until IS NULL)) ORDER BY f.name LIMIT 30",
        )
        sheets = store.rows(
            c,
            "SELECT f.name,s.sheet,s.number,s.title FROM map_sheets s "
            "JOIN files f ON f.id=s.file_id "
            "WHERE s.valid_until IS NULL AND f.valid_until IS NULL "
            "AND (s.sheet<>'Model' OR NOT EXISTS (SELECT 1 FROM map_sheets p "
            "WHERE p.file_id=s.file_id AND p.sheet<>'Model' AND p.valid_until IS NULL)) "
            "ORDER BY coalesce(s.number,''),f.id,s.sheet,s.id LIMIT 20",
        )
        drawing_count = c.execute(
            "SELECT count(*) FROM files f WHERE valid_until IS NULL AND "
            "(kind IN ('dwg','dxf') OR EXISTS (SELECT 1 FROM map_sheets s "
            "WHERE s.file_id=f.id AND s.valid_until IS NULL))"
        ).fetchone()[0]
    if drawing_count:
        lines.append(f"Drawing files: {drawing_count}; drawing sheets: {sheet_count}")
        for drawing in drawing_names:
            lines.append(f"Drawing file: {drawing['id']} | {drawing['name']}")
        for sheet in sheets:
            lines.append(
                f"{sheet['name'][:60]} | {sheet['sheet'][:40]} | "
                f"{(sheet['number'] or 'unknown')[:40]} | {(sheet['title'] or 'unknown')[:100]}"
            )
        lines.append(
            "Sheets: project_map mode sheets; page until next_page is null. "
            "Block counts: mode counts"
        )

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
    for line in candidates:
        if len(("\n".join(lines) + "\n" + line).encode()) <= 1200:
            lines.append(line)
    facts = tender_facts(rec)
    if facts:
        lines.append(
            "Tender summary (grounded evidence; cite source; preserve verification/conflicts):"
        )
        lines.extend(json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in facts)
    return "\n".join(lines) if len(lines) > 1 else ""
