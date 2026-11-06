"""Sourced local drawing evidence shared by file and passage readers."""

import json
from collections import Counter

from qsone.records.mapping import store


def chunks(rec, info):
    if info.kind not in {"dwg", "dxf"}:
        return []
    with rec.read() as c:
        sheets = store.rows(
            c,
            "SELECT * FROM map_sheets WHERE file_id=? AND valid_until IS NULL ORDER BY id",
            (info.id,),
        )
    result, total = [], Counter()
    for sheet in sheets:
        loc = {"sheet": sheet["sheet"]}
        source = f"{info.name} | layout {sheet['sheet']}"
        metadata = " | ".join(
            f"{key}: {sheet[key] or 'unknown'}" for key in ("number", "title", "revision", "scale")
        )
        result.append((loc, f"{source} | {metadata}"))
    for sheet in sheets:
        counts = json.loads(sheet["counts"])
        total.update(counts)
        loc = {"sheet": sheet["sheet"]}
        for name, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:30]:
            result.append((loc, f"{info.name} | layout {sheet['sheet']} | {name} × {count}"))
        if len(counts) > 30:
            result.append(
                (
                    loc,
                    f"{info.name} | layout {sheet['sheet']} | remaining blocks: "
                    f"project_map mode counts file_id={info.id}",
                )
            )
    for name, count in total.most_common(30):
        result.append(({}, f"{info.name} | file total (all layouts) | {name} × {count}"))
    return result
