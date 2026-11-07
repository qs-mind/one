"""Bounded navigation and grounded Tender summary for the Lead's first request."""

import json

from qsone.records.mapping import store
from qsone.records.mapping.roles import file_role

# Facts are evidence already grounded by the map; labels/key pages remain navigation.
FACT_BYTES = 6000
DIGEST_FACT_BYTES = 1000
DIGEST_DRAWING_BYTES = 1500
DIGEST_FILE_BYTES = 400


def _short(value, limit):
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _section(header, entries, total, budget, mode):
    """Budget includes headings, separators and the exact omitted-count footer."""
    lines = [header]
    shown = 0
    for entry in entries:
        remaining = total - shown - 1
        footer = [f"{remaining} more: project_map mode {mode}"] if remaining else []
        if len("\n".join([*lines, entry, *footer]).encode()) > budget:
            break
        lines.append(entry)
        shown += 1
    if total > shown:
        lines.append(f"{total - shown} more: project_map mode {mode}")
    return "\n".join(lines)


def tender_facts(rec, *, preview=False):
    """Full bounded truth-check evidence; optional shortened first-request previews."""
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
        if not preview and fact.get("source_label"):
            item["source_label"] = fact["source_label"]
        if preview:
            item["name"] = {lang: _short(text, 60) for lang, text in item["name"].items()}
            item["value"] = _short(item["value"], 120)
            item["file"] = _short(item["file"], 60)
        length = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode())
        if preview or size + length <= FACT_BYTES:
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
        fact_states = dict(
            c.execute(
                "SELECT a.state,count(*) FROM map_facts a JOIN files f ON f.id=a.file_id "
                "WHERE a.valid_until IS NULL AND f.valid_until IS NULL GROUP BY a.state"
            ).fetchall()
        )
        page_total = c.execute(
            "SELECT count(*) FROM map_files m JOIN files f ON f.id=m.file_id "
            "WHERE m.valid_until IS NULL AND f.valid_until IS NULL AND m.key_pages != '[]'"
        ).fetchone()[0]
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
        heading = f"Drawing files: {drawing_count}; drawing sheets: {sheet_count}"
        names = _section(
            heading,
            [f"Drawing file: {d['id']} | {_short(d['name'], 60)}" for d in drawing_names],
            drawing_count,
            450,
            "sheets",
        )
        guidance = (
            "Sheets: project_map mode sheets; page until next_page is null. "
            "Block counts: mode counts"
        )
        sheet_lines = [
            f"{_short(s['name'], 60)} | {_short(s['number'] or s['sheet'], 40)} | "
            f"{_short(s['title'] or 'unknown', 60)}"
            for s in sheets
        ]
        lines.append(
            _section(
                names,
                sheet_lines,
                sheet_count,
                DIGEST_DRAWING_BYTES - len(guidance.encode()) - 1,
                "sheets",
            )
            + "\n"
            + guidance
        )

    candidates = []
    for row in pages:
        key_pages = json.loads(row["key_pages"])
        candidates.append(
            json.dumps(
                {
                    "file_id": row["file_id"],
                    "file": _short(row["name"], 60),
                    "role": file_role(row["folder"], row["ai_kind"]),
                    "key_pages": [
                        {
                            **page,
                            "label": {
                                lang: _short(text, 60) for lang, text in page["label"].items()
                            },
                        }
                        for page in key_pages[:3]
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    if page_total:
        lines.append(
            _section(
                "Files/key pages:",
                candidates,
                page_total,
                DIGEST_FILE_BYTES,
                "overview",
            )
        )
    facts = tender_facts(rec, preview=True)
    if fact_states:
        header = (
            "Tender summary (previews; cite source; preserve verification/conflicts): "
            + ", ".join(f"{state}: {count}" for state, count in sorted(fact_states.items()))
        )
        lines.append(
            _section(
                header,
                [json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in facts],
                sum(fact_states.values()),
                DIGEST_FACT_BYTES,
                "facts",
            )
        )
    return "\n".join(lines) if len(lines) > 1 else ""
