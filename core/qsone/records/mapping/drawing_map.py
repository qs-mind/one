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
        boq_pages = {
            json.loads(locator).get("page")
            for (locator,) in c.execute(
                "SELECT locator FROM map_tables WHERE file_id=? "
                "AND looks_like_boq=1 AND valid_until IS NULL",
                (info.id,),
            )
        }
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
            if page.page_number in boq_pages:
                page.close()
                continue
            positioned = words.get(page.page_number) or [
                word | {"page": page.page_number} for word in page.extract_words()
            ]
            sheet = drawings.read_pdf_sheet(positioned, (page.width, page.height))
            # Title-block-like phrases can occur in prose too. Judge all positioned
            # text, including OCR, before admitting either title or geometry evidence.
            lines = sheet.texts
            total_words = sum(len(line["text"].split()) for line in lines)
            running_words = sum(
                len(line["text"].split()) for line in lines if len(line["text"].split()) >= 8
            )
            running_text = bool(total_words and running_words / total_words >= 0.25)
            short = [line for line in lines if len(line["text"].split()) <= 6]

            def area(line):
                x0, top, x1, bottom = line["box"]
                return max(0, x1 - x0) * max(0, bottom - top)

            text_area = sum(map(area, lines))
            labels_dominate = bool(text_area and sum(map(area, short)) / text_area >= 0.8)
            spread = bool(short) and (
                max(line["box"][2] for line in short) - min(line["box"][0] for line in short)
                >= page.width * 0.25
                and max(line["box"][3] for line in short) - min(line["box"][1] for line in short)
                >= page.height * 0.25
            )
            vectors = len(page.lines) + len(page.curves) + len(page.rects)
            # Sparse text can live entirely in a corner of an architectural plan.
            # Thousands of paths, overwhelmingly more than words, are an alternate
            # geometry signal; prose/BOQ guards and file coverage still apply.
            vector_dominated = vectors >= 1000 and vectors >= 20 * max(1, total_words)
            geometric_plan = (
                max(page.width, page.height) >= 1000
                and vectors >= 40
                and labels_dominate
                and (spread or vector_dominated)
            )
            if not running_text and (
                geometric_plan
                or (sheet.number and sheet.title)
                or (
                    max(page.width, page.height) > 1000
                    and sheet.number
                    and (sheet.title or sheet.scale)
                )
            ):
                sheet.layout = str(page.page_number)
                sheet.source["page"] = page.page_number
                sheet.source["page_size"] = [page.width, page.height]
                # The worker persisted these page types from pdf-inspector before OCR.
                sheet.source["page_type"] = "scan" if page.page_number in scanned else "text"
                result.append(sheet)
            page.close()
    return result


def is_drawing_file(sheets, pages):
    """Embedded diagrams stay citable sheets, but cannot reclassify a text document."""
    return bool(pages and len({s.source.get("page") for s in sheets}) > pages / 2)


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
        if sheets and (info.kind != "pdf" or is_drawing_file(sheets, info.pages)):
            store.write(c, rec, "map_files", {"file_id": file_id, "ai_kind": "drawing"})
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
