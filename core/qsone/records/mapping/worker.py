"""One durable slice per call: structure a file, OCR one page, or finish it.

Only original bytes in memory reach the PDF readers. No decrypted PDF is written.
"""

import logging
import re

import pdf_inspector

from qsone import copy
from qsone.records import boq, files, ocr
from qsone.records.mapping import facts, links, store

log = logging.getLogger(__name__)


class FilePass:
    """One original and OCR setup, reused across page slices; never a file queue."""

    def __init__(self):
        self.clear()

    def clear(self):
        self.key = None
        self.data = None
        self.ocr_config = None

    def __call__(self, rec, file_id):
        if self.key != (rec, file_id):
            self.clear()
            self.data = files.read_original(rec, file_id)
            self.key = (rec, file_id)
        return self.data

    def languages(self):
        if self.ocr_config is None:
            executable = ocr.find_tesseract()
            languages = ocr.find_languages(executable) if executable else None
            self.ocr_config = executable, languages
        return self.ocr_config


def _table(sheet, locator):
    header, columns = boq.guess(sheet, sheet.last_row)
    return {
        "locator": locator,
        "header": [boq._text(c.value) for _, c in sorted(sheet.cells.get(header or 1, {}).items())],
        "row_count": sheet.last_row,
        "looks_like_boq": int(bool(columns)),
        "column_guess": columns,
        # No calibrated probability is supplied by the local column matcher.
        "confidence": None,
    }


def _pdf(data, info, text_pages):
    classification = pdf_inspector.classify_pdf_bytes(data)
    markdown = pdf_inspector.extract_pages_markdown_bytes(data)
    # pdf-inspector page indices are zero based; ONE locators are one based.
    scanned = {n + 1 for n in classification.pages_needing_ocr}
    pages, headings = [], []
    for p in markdown.pages:
        number = p.page + 1
        if p.needs_ocr or not p.markdown.strip():
            scanned.add(number)
        pages.append({"page": number, "markdown": p.markdown})
        for line in p.markdown.splitlines():
            match = re.match(r"^(#{1,4})\s+(.+)", line)
            if match:
                headings.append({"page": number, "level": len(match[1]), "text": match[2]})
    # Independent check from ONE's already-stored original text extraction.
    scanned.update(set(range(1, classification.page_count + 1)) - text_pages)
    tables = _pdf_tables(data, table_pages=set(markdown.pages_with_tables))
    elements = [
        {"page": e.page, "role": e.role, "mcid": e.mcid}
        for e in pdf_inspector.extract_structure_elements_bytes(data)
    ]
    return (
        {"pages": pages, "headings": headings, "sections": headings, "elements": elements},
        sorted(scanned),
        tables,
    )


def _pdf_tables(data, *, ocr_words=None, table_pages=None):
    """Find geometry once per page; reuse ONE's cell reading and BOQ matcher.

    The BOQ import reader also builds numeric import origins by reopening the
    whole PDF per page. Mapping only needs table bounds, so avoids that work.
    """
    import io

    import pdfplumber

    from qsone.records import boq_pdf

    if table_pages is None:
        table_pages = set(pdf_inspector.extract_pages_markdown_bytes(data).pages_with_tables)
    result = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            if not page.chars and ocr_words:
                page.objects["char"] = boq_pdf._ocr_chars(page, ocr_words.get(page.page_number, []))
            if not page.chars:
                page.close()
                continue
            found = page.find_tables()
            borderless = not found
            if borderless:
                found = page.find_tables(
                    {"vertical_strategy": "text", "horizontal_strategy": "text"}
                )
            left, top = page.cropbox[:2]
            for table in found:
                candidate = boq.Sheet("", False)
                for r, row in enumerate(table.rows, 1):
                    for col, box in enumerate(row.cells, 1):
                        if box is None:
                            continue
                        x0, y0, x1, y1 = box
                        chars = [
                            ch
                            for ch in page.chars
                            if x0 <= (ch["x0"] + ch["x1"]) / 2 < x1
                            and y0 <= (ch["top"] + ch["bottom"]) / 2 < y1
                        ]
                        candidate.cells.setdefault(r, {})[col] = boq.Cell(
                            boq_pdf.cell_text(chars), None
                        )
                _, columns = boq.guess(candidate, candidate.last_row)
                if borderless and page.page_number not in table_pages and not columns:
                    continue  # aligned prose needs neither a table tag nor a BOQ header
                x0, y0, x1, y1 = table.bbox
                result.append(
                    _table(
                        candidate,
                        {
                            "page": page.page_number,
                            "box": [x0 - left, y0 - top, x1 - left, y1 - top],
                            "rows": [1, len(table.rows)],
                            "cols": [1, max((len(r.cells) for r in table.rows), default=0)],
                        },
                    )
                )
            # pdfplumber retains per-page caches otherwise; a big tender must stay bounded.
            page.close()
    return result


def _structure(rec, info, data):
    if info.kind == "pdf":
        with rec.read() as c:
            text_pages = {
                int(p)
                for (p,) in c.execute(
                    "SELECT DISTINCT json_extract(locator, '$.page') FROM chunks WHERE file_id=? "
                    "AND trim(text)<>'' AND json_extract(locator, '$.read_by') IS NULL",
                    (info.id,),
                )
            }
        return _pdf(data, info, text_pages)
    structure = {"headings": [], "sections": [], "numbered_clauses": [], "sheets": []}
    tables = []
    if info.kind in ("xlsx", "xls"):
        reader = boq._xlsx if info.kind == "xlsx" else boq._xls
        names, _ = reader(data, None)
        for name, _ in names:
            _, sheet = reader(data, name)
            header, columns = boq.guess(sheet, sheet.last_row)
            totals = [
                r
                for r, cells in sheet.cells.items()
                if any(
                    re.search(
                        r"\b(?:grand total|total|subtotal)\b|الإجمالي|الاجمالي|إجمالي",
                        boq._text(c.value),
                        re.I,
                    )
                    for c in cells.values()
                )
            ]
            structure["sheets"].append(
                {
                    "name": name,
                    "header_row": header,
                    "totals_rows": totals,
                    "last_row": sheet.last_row,
                }
            )
            tables.append(
                _table(
                    sheet,
                    {
                        "sheet": name,
                        "rows": [1, sheet.last_row],
                        "cols": [
                            1,
                            max((max(r, default=0) for r in sheet.cells.values()), default=0),
                        ],
                    },
                )
            )
    elif info.kind == "docx":
        from qsone.records.readers import docx

        pieces, _, _ = docx.read(data)
        for piece in pieces:
            entry = piece.locator | {"text": piece.text}
            if piece.locator.get("heading") == piece.text:
                structure["headings"].append(entry)
                structure["sections"].append(entry)
            if re.match(r"^\s*\d+(?:\.\d+)*[.)]?\s+", piece.text):
                structure["numbered_clauses"].append(entry)
        # Numbered list paragraphs can have numbering in XML rather than printed text.
        import io

        import docx as word
        from docx.oxml.ns import qn

        document = word.Document(io.BytesIO(data))
        for n, para in enumerate(document.paragraphs, 1):
            if para._p.find(".//" + qn("w:numPr")) is not None:
                visible = next((p.text for p in pieces if p.locator.get("paragraph") == n), None)
                if visible and not any(
                    e.get("paragraph") == n for e in structure["numbered_clauses"]
                ):
                    structure["numbered_clauses"].append({"paragraph": n, "text": visible})
    return structure, [], tables


def _update(rec, file_id, fields, tables=None):
    with rec.write(store.ACTOR) as c:
        if (
            c.execute(
                "SELECT 1 FROM files WHERE id=? AND valid_until IS NULL", (file_id,)
            ).fetchone()
            is None
        ):
            return
        store.write(c, rec, "map_files", {"file_id": file_id} | fields)
        if tables is not None:
            old = store.rows(
                c, "SELECT id FROM map_tables WHERE file_id=? AND valid_until IS NULL", (file_id,)
            )
            for row in old:
                store.write(c, rec, "map_tables", row | {"valid_until": rec.clock()})
            for table in tables:
                store.write(c, rec, "map_tables", table | {"file_id": file_id})


def _pending(rec):
    with rec.read() as c:
        return store.rows(
            c,
            "SELECT m.* FROM map_files m JOIN files f ON f.id=m.file_id "
            "WHERE m.valid_until IS NULL AND local_state IN ('waiting','reading') "
            "ORDER BY local_state,f.rowid LIMIT 1",
        )


def step(
    rec,
    *,
    cancelled=lambda: False,
    original=None,
    fact_read=None,
    fact_propose=None,
    link_digests=None,
    link_propose=None,
):
    """Resume waiting/reading records, with no in-memory queue. Returns whether work existed."""
    original = original if original is not None else FilePass()
    if cancelled():
        original.clear()
        return False
    pending = _pending(rec)
    if not pending:
        store.seed(rec)
        pending = _pending(rec)
    if not pending:
        original.clear()
        return False
    row = store.decoded(pending[0])
    file_id = row["file_id"]
    info = files.file_info(rec, file_id)
    try:
        if row["local_state"] == "waiting":
            if _duplicate(rec, file_id):
                original.clear()
                return True
            data = original(rec, file_id)
            structure, scanned, tables = _structure(rec, info, data)
            _update(
                rec,
                file_id,
                {
                    "local_state": "reading",
                    "structure": structure,
                    "scanned_pages": scanned,
                    "text_pages": (info.pages or 0) - len(scanned),
                    "read_how": "text" if info.chunks else "stored",
                },
                tables,
            )
            return True
        scanned = row["scanned_pages"]
        with rec.read() as c:
            read = {
                int(n)
                for (n,) in c.execute(
                    "SELECT DISTINCT json_extract(locator, '$.page') FROM chunks "
                    "WHERE file_id=? AND json_extract(locator, '$.read_by') IS NOT NULL",
                    (file_id,),
                )
            }
        remaining = [p for p in scanned if p not in read]
        if remaining:
            data = original(rec, file_id)
            executable, languages = original.languages()
            if not executable:
                _update(rec, file_id, {"local_state": "failed", "note": copy.OCR_TESSERACT_MISSING})
                original.clear()
                return True
            if not languages:
                _update(rec, file_id, {"local_state": "failed", "note": copy.OCR_TESSERACT_FAILED})
                original.clear()
                return True
            note = copy.MAP_ARABIC_MISSING if "ara" not in languages[1].split("+") else row["note"]
            if cancelled():
                return False
            from qsone.tools.files import _local_page

            page = remaining[0]
            result = _local_page(data, info.kind, page, executable, *languages)
            if cancelled():
                return False
            files.add_ocr_pages(
                rec,
                file_id,
                {page: result.pieces(page)},
                read_by="tesseract",
                actor=store.ACTOR,
                include_text_pages=True,
            )
            _update(
                rec,
                file_id,
                {
                    "ocr_done_pages": sorted(set(row["ocr_done_pages"]) | {page}),
                    "note": note,
                    "read_how": "mixed" if row["text_pages"] else "ocr",
                },
            )
            return True
        tables = None
        if scanned:
            # The BOQ reader reuses the persisted OCR words and their exact source boxes.
            with rec.read() as c:
                chunks = c.execute(
                    "SELECT locator,text FROM chunks WHERE file_id=?", (file_id,)
                ).fetchall()
            import json

            words = {}
            for loc, text in chunks:
                loc = json.loads(loc)
                if loc.get("read_by") == "tesseract" and "box" in loc:
                    words.setdefault(loc["page"], []).append({"text": text, "box": loc["box"]})
            tables = _pdf_tables(original(rec, file_id), ocr_words=words)
        from qsone.records.mapping import drawing_map, remap

        drawing_map.populate(rec, file_id, original(rec, file_id))
        remap.revalidate(rec, file_id)
        _update(
            rec,
            file_id,
            {
                "local_state": "done",
                "mapped_at": rec.clock(),
                "ocr_done_pages": sorted(set(scanned) & read),
                "read_how": ("mixed" if row["text_pages"] else "ocr")
                if scanned
                else row["read_how"],
            },
            tables,
        )
        links.step(rec, file_id, digests=link_digests, propose=link_propose)
        facts.step(rec, read=fact_read, propose=fact_propose)
        original.clear()
    except Exception as error:
        # Exception messages and traceback source lines may contain private file text.
        # Retain stack locations without exception messages or source lines.
        frames = []
        trace = error.__traceback__
        while trace is not None:
            code = trace.tb_frame.f_code
            frames.append(f"{code.co_filename}:{code.co_name}:{trace.tb_lineno}")
            trace = trace.tb_next
        log.warning(
            "Project map failed: project=%s file=%s stage=%s cause=%s stack=%s",
            rec.id,
            file_id,
            row["local_state"],
            type(error).__name__,
            frames,
        )
        original.clear()
        _update(rec, file_id, {"local_state": "failed", "note": copy.MAP_FAILED})
    return True


def _duplicate(rec, file_id):
    """Reuse the first locally mapped identical original, including bounded evidence rows."""
    with rec.write(store.ACTOR) as c:
        found = c.execute(
            "SELECT m.file_id FROM map_files m JOIN files f ON f.id=m.file_id "
            "WHERE f.sha256=(SELECT sha256 FROM files WHERE id=?) AND f.id<>? "
            "AND f.rowid<(SELECT rowid FROM files WHERE id=?) "
            "AND m.local_state='done' ORDER BY f.rowid LIMIT 1",
            (file_id, file_id, file_id),
        ).fetchone()
        if not found:
            return False
        source = store.decoded(store.rows(c, "SELECT * FROM map_files WHERE file_id=?", found)[0])
        fields = {
            k: source[k]
            for k in (
                "structure",
                "scanned_pages",
                "ocr_done_pages",
                "text_pages",
                "read_how",
                "ai_kind",
                "ai_title",
                "ai_group",
                "key_pages",
                "note",
            )
        }
        store.write(
            c,
            rec,
            "map_files",
            fields
            | {
                "file_id": file_id,
                "local_state": "done",
                "ai_state": "local",
                "mapped_at": rec.clock(),
            },
        )
        for table in ("map_tables", "map_sheets"):
            for row in store.rows(
                c, f"SELECT * FROM {table} WHERE file_id=? AND valid_until IS NULL", found
            ):
                item = store.decoded(row)
                item.pop("id")
                store.write(c, rec, table, item | {"file_id": file_id})
        return True
