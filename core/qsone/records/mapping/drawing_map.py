"""Populate drawing evidence through the public local readers, and pair revisions."""

import io
import json
from dataclasses import asdict

from qsone import copy
from qsone.records import drawings, files
from qsone.records.mapping import store


def read(rec, info, data):
    if info.kind in ("dwg", "dxf"):
        return drawings.read_sheets(info.name, data)
    if info.kind != "pdf":
        return []
    import pdfplumber

    with rec.read() as c:
        chunks = c.execute("SELECT locator,text FROM chunks WHERE file_id=?", (info.id,)).fetchall()
        scanned = set(
            json.loads(
                c.execute(
                    "SELECT scanned_pages FROM map_files WHERE file_id=?", (info.id,)
                ).fetchone()[0]
            )
        )
    words = {}
    for raw, text in chunks:
        loc = json.loads(raw)
        if loc.get("read_by") and len(loc.get("box", [])) == 4:
            x0, top, x1, bottom = loc["box"]
            words.setdefault(loc["page"], []).append(
                dict(text=text, x0=x0, top=top, x1=x1, bottom=bottom, page=loc["page"])
            )
    result = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            positioned = words.get(page.page_number) or [
                word | {"page": page.page_number} for word in page.extract_words()
            ]
            sheet = drawings.read_pdf_sheet(positioned, (page.width, page.height))
            # Title-block evidence is mandatory, even on a large sheet.
            if (sheet.number and sheet.title) or (
                max(page.width, page.height) > 1000 and (sheet.number or sheet.title or sheet.scale)
            ):
                sheet.layout = str(page.page_number)
                sheet.source["page"] = page.page_number
                sheet.source["page_size"] = [page.width, page.height]
                # The worker persisted these page types from pdf-inspector before OCR.
                sheet.source["page_type"] = "scan" if page.page_number in scanned else "text"
                result.append(sheet)
            page.close()
    return result


def populate(rec, file_id, data):
    info = files.file_info(rec, file_id)
    sheets = read(rec, info, data)
    with rec.write(store.ACTOR) as c:
        if not c.execute(
            "SELECT 1 FROM files WHERE id=? AND valid_until IS NULL", (file_id,)
        ).fetchone():
            return
        for old in store.rows(
            c, "SELECT id FROM map_sheets WHERE file_id=? AND valid_until IS NULL", (file_id,)
        ):
            store.write(c, rec, "map_sheets", old | {"valid_until": rec.clock()})
        for old in store.rows(
            c,
            "SELECT id FROM map_links WHERE kind='revision' AND \"by\"='one' AND (from_file_id=? "
            "OR to_file_id=?) AND valid_until IS NULL",
            (file_id, file_id),
        ):
            store.write(c, rec, "map_links", old | {"valid_until": rec.clock()})
        for sheet in sheets:
            row = asdict(sheet)
            store.write(
                c,
                rec,
                "map_sheets",
                {
                    "file_id": file_id,
                    "sheet": sheet.layout,
                    "number": sheet.number,
                    "title": sheet.title,
                    "revision": sheet.revision,
                    "date": sheet.date,
                    "scale": sheet.scale,
                    "discipline": sheet.discipline_hint,
                    "counts": row["counts"],
                    "rooms": row["rooms"],
                    "source": row["source"]
                    | ({"words": row["texts"]} if not sheet.number or not sheet.title else {}),
                    "state": "local",
                },
            )
            if not sheet.number or not sheet.revision:
                continue
            matches = store.rows(
                c,
                "SELECT * FROM map_sheets WHERE number=? AND file_id<>? AND revision IS NOT "
                "NULL AND revision<>? AND valid_until IS NULL",
                (sheet.number, file_id, sheet.revision),
            )
            for other in matches:
                store.write(
                    c,
                    rec,
                    "map_links",
                    {
                        "from_file_id": other["file_id"],
                        "from_locator": {"sheet": other["sheet"]},
                        "to_file_id": file_id,
                        "to_locator": {"sheet": sheet.layout},
                        "kind": "revision",
                        "words": copy.MAP_REVISION,
                        "evidence": {
                            "number": sheet.number,
                            "revisions": [other["revision"], sheet.revision],
                        },
                        "by": "one",
                        "state": "found",
                    },
                )
