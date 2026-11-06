"""Local drawing evidence. Geometry yields candidates, never inferred sheet facts.

The subprocess receives decrypted bytes only through stdin. No drawing is written to disk.
PDF callers may supply stored OCR words in pdfplumber's word-box shape.
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field, fields
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from .arabic import decode_text


@dataclass
class Drawing:
    name: str = ""
    format: str = ""
    version: str = ""
    units: int = 0
    extents: list[float] = field(default_factory=list)
    styles: list[dict] = field(default_factory=list)
    embedded: list[dict] = field(default_factory=list)
    entity_kinds: dict = field(default_factory=dict)
    summary_info: dict = field(default_factory=dict)
    layers: list[dict] = field(default_factory=list)
    layouts: list[dict] = field(default_factory=list)
    texts: list[dict] = field(default_factory=list)
    inserts: list[dict] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    dimensions: list[dict] = field(default_factory=list)
    hatches: list[dict] = field(default_factory=list)
    closed: list[dict] = field(default_factory=list)
    xrefs: list[dict] = field(default_factory=list)
    problems: list = field(default_factory=list)
    omitted: dict = field(default_factory=dict)
    traversal_limited: bool = False
    totals: dict = field(default_factory=dict)
    note: str | None = None
    repaired: bool = False


@dataclass
class Room:
    name: str
    area_m2: float | None
    outline: list[float]
    source: dict
    candidate: bool = True


@dataclass
class Sheet:
    layout: str = "Model"
    number: str | None = None
    title: str | None = None
    revision: str | None = None
    date: str | None = None
    scale: str | None = None
    project: str | None = None
    client: str | None = None
    consultant: str | None = None
    discipline_hint: str | None = None
    counts_complete: bool = True
    rooms_complete: bool = True
    counts: dict[str, int] = field(default_factory=dict)
    rooms: list[Room] = field(default_factory=list)
    texts: list[dict] = field(default_factory=list)
    source: dict[str, dict | list] = field(default_factory=dict)


def find_binary() -> Path | None:
    name = "qsone-drawings" + (".exe" if os.name == "nt" else "")
    explicit = os.environ.get("QSONE_DRAWINGS")
    candidates = [Path(explicit)] if explicit else []
    # Embedded Python lives at core/python.exe on Windows and core/bin/python3 elsewhere.
    executable = Path(sys.executable).resolve()
    candidates += [executable.parent / name, executable.parent.parent / name]
    for parent in Path(__file__).resolve().parents:
        if (parent / "drawings" / "Cargo.toml").is_file():
            candidates.append(parent / "drawings" / "target" / "release" / name)
            break
    return next((p for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)


def _display_text(row: dict) -> dict:
    row = decode_text(row)
    return {**row, "text": re.sub(r"%%[uUoOkK]", "", row["text"]).strip()}


def read_drawing(name: str, data: bytes) -> Drawing:
    binary = find_binary()
    if binary is None:
        return Drawing(note="FILE_DRAWINGS_MISSING")
    if len(data) > 64 * 1024 * 1024:
        return Drawing(note="FILE_DRAWINGS_LIMIT")
    try:
        result = subprocess.run(
            [str(binary), "--name", name],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        if result.returncode not in (0, 2) or len(result.stdout) > 64 * 1024 * 1024:
            return Drawing(note="FILE_UNREADABLE")
        raw = json.loads(result.stdout)
        allowed = {f.name for f in fields(Drawing)} - {"note", "repaired"}
        drawing = Drawing(**{k: v for k, v in raw.items() if k in allowed})
        if not isinstance(drawing.texts, list) or not isinstance(drawing.inserts, list):
            return Drawing(note="FILE_UNREADABLE")
        drawing.name = name
        drawing.texts = [_display_text(t) for t in drawing.texts]
        decoded_attributes = {t.get("handle"): t for t in drawing.texts}
        for insert in drawing.inserts:
            for attr in insert.get("attributes", []):
                attr["raw_value"] = attr["value"]
                attr["value"] = decoded_attributes.get(attr.get("handle"), {}).get(
                    "text", re.sub(r"%%[uUoOkK]", "", attr["value"]).strip()
                )
        _embedded_texts(drawing)
        drawing.repaired = result.returncode == 2 or bool(drawing.problems)
        if drawing.repaired:
            drawing.note = "FILE_DRAWINGS_REPAIRED"
        return drawing
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return Drawing(note="FILE_UNREADABLE")


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DISCIPLINES = {
    "A": "architecture",
    "S": "structure",
    "M": "mechanical",
    "E": "electrical",
    "EL": "electrical",
    "P": "plumbing",
    "C": "civil",
    "L": "landscape",
}
_LABELS = {
    "number": (
        r"(?:sheet[\s_-]*(?:no\.?|number)|drawing[\s_-]*(?:no\.?|number)"
        r"|dwg[\s_-]*no|رقم\s*المخطط|رقم\s*اللوح[ةه]|لوح[ةه]\s*رقم)"
    ),
    "title": (
        r"(?:title|sheet[\s_-]*title|drawing[\s_-]*title|عنوان\s*اللوح[ةه]"
        r"|اسم\s*اللوح[ةه]|(?:top|bottom)[- ]title)"
    ),
    "revision": r"(?:rev(?:ision)?\.?|المراجع[ةه]|رقم\s*المراجع[ةه]|الإصدار|تعديل)",
    "date": r"(?:date|التاريخ|تاريخ)",
    "scale": r"(?:scale|مقياس\s*الرسم|المقياس)",
    "project": r"(?:project(?: name)?|المشروع|اسم المشروع)",
    "client": r"(?:client|owner|المالك)",
    "consultant": r"(?:consultant|الاستشاري)",
}
_SCALE = re.compile(r"(?<!\d)(\d+)\s*[:/]\s*(\d+)(?!\d)")
_SHEET_NO = re.compile(r"(?:[A-Za-z]{1,4}|[\u0621-\u064a]{1,3})\s*[-–]\s*\d+[A-Za-z]?", re.I)


def _source(row: dict) -> dict:
    if "box" in row:
        return {"page": row.get("page", 1), "box": row["box"]}
    return {
        k: row[k]
        for k in ("layout", "handle", "x", "y", "block", "table_cell", "embedded_sheet", "context")
        if k in row
    }


def _value(key: str, text: str) -> str | None:
    text = text.translate(_DIGITS).strip(" :：=\t\n")
    if any(re.fullmatch(pattern, text, re.I) for pattern in _LABELS.values()):
        return None
    if key == "scale":
        if text.upper() == "NTS" or text == "لا يوجد مقياس":
            return text
        m = _SCALE.fullmatch(text)
        if m and (
            (int(m[1]) == 1 and 1 <= int(m[2]) <= 100000)
            or (int(m[2]) == 1 and 1 <= int(m[1]) <= 100000)
        ):
            return f"{int(m[1])}:{int(m[2])}"
        return None
    if key == "number":
        m = _SHEET_NO.fullmatch(text)
        if m and not re.match(r"(?:RJ|CAT|IP|ISO|BS|DIN|IEC|EN|RS|USB|DB|RG)[ -]", text, re.I):
            return re.sub(r"\s+", "", m[0]).replace("–", "-")
        return None
    if key == "revision":
        return text if re.fullmatch(r"[A-Za-z0-9]{1,4}(?:[.-][A-Za-z0-9]{1,2})?", text) else None
    if key == "title" and (_value("number", text) or _value("scale", text)):
        return None
    if key == "date":
        return text if re.fullmatch(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}", text) else None
    return text or None


def _assign(sheet: Sheet, key: str, value: str | None, row: dict):
    if value and getattr(sheet, key) is None:
        setattr(sheet, key, value)
        sheet.source[key] = _source(row)


_FRAME = re.compile(r"frame|title|paper[ _-]*layout|لوح[ةه]|اطار", re.I)
_EXCLUDE = re.compile(
    r"frame|title|paper[ _-]*layout|legend|schedule|table|hatch|border|جدول|مفتاح", re.I
)


def _label(text: str) -> str | None:
    return next(
        (k for k, p in _LABELS.items() if re.fullmatch(p, text.strip(" :：\n"), re.I)), None
    )


def _title(
    sheet: Sheet,
    rows: list[dict],
    inserts: list[dict],
    bounds: tuple,
    outlines=None,
    file_number=None,
    segments=None,
):
    left, bottom, right, top = bounds
    width, height = max(right - left, 1), max(top - bottom, 1)
    frame_names = {i["block"] for i in inserts if _FRAME.search(i["block"])}
    if not frame_names:
        bordered = []
        for i in inserts:
            box = i.get("bounds", [])
            if len(box) == 4:
                x0, y0, x1, y1 = box
                if (
                    x1 - x0 >= width * 0.5
                    and y1 - y0 >= height * 0.5
                    and (abs(x0 - left) < width * 0.1 or abs(x1 - right) < width * 0.1)
                ):
                    bordered.append(((x1 - x0) * (y1 - y0), i["block"]))
        if bordered:
            frame_names.add(max(bordered)[1])
    structured = [
        r for r in rows if r.get("block") in frame_names or _FRAME.search(r.get("block", ""))
    ]
    # A frame's attributes belong to that instance, even if their positions are
    # outside the sheet extents because the source CAD attribute is malformed.
    attributed = [
        i
        for i in inserts
        if i["block"] in frame_names or any(_label(a["tag"]) for a in i.get("attributes", []))
    ]
    for insert in attributed:
        for attr in insert.get("attributes", []):
            key = _label(attr["tag"])
            value = attr.get("value", "")
            if key:
                _assign(sheet, key, _value(key, value), {**insert, **attr})
            # Some legacy blocks misname their attribute; syntax is evidence.
            if re.fullmatch(r"drawing[ _-]*title", attr["tag"], re.I) and not file_number:
                _assign(sheet, "number", _value("number", value), {**insert, **attr})
            if key == "title":
                _assign(sheet, "scale", _value("scale", value), {**insert, **attr})
    # Without an explicit frame, use the region with the densest title labels.
    labels = [
        r
        for r in rows
        if _label(r["text"])
        or any(
            re.match(rf"^\s*{pattern}\s*[:：=]", r["text"], re.I) for pattern in _LABELS.values()
        )
    ]
    if structured:
        candidates = structured
    elif labels:
        candidates = rows
    else:
        candidates = [
            r
            for r in rows
            if r.get("x", 0) >= right - width * 0.4 and r.get("y", 0) <= bottom + height * 0.4
        ]
    cells = []
    for o in outlines or []:
        if len(o.get("vertices", [])) >= 3:
            polygon = Polygon(o["vertices"])
            if polygon.is_valid and polygon.area > 0:
                cells.append(polygon)
    for row in candidates:
        text = row["text"].translate(_DIGITS).strip()
        for key, pattern in _LABELS.items():
            m = re.fullmatch(rf"{pattern}\s*[:：=]?\s+(.+)", text, re.I)
            if m:
                _assign(sheet, key, _value(key, m[1]), row)
        key = _label(text)
        if not key:
            continue
        h = max(row.get("height", 3), 1)
        cell = min(
            (p for p in cells if p.covers(Point(row["x"], row["y"]))),
            key=lambda p: p.area,
            default=None,
        )
        nearby = []
        for r in candidates:
            if r is row or _label(r["text"]) or r.get("table_cell"):
                continue
            if row.get("block") and r.get("block") != row.get("block"):
                continue
            dx, dy = r["x"] - row["x"], r["y"] - row["y"]
            if not (
                (0 < dx <= h * 35 and abs(dy) <= h * 0.8)
                or (abs(dx) <= h * 12 and -h * 8 <= dy < -h * 0.8)
            ):
                continue
            if cell is not None and not cell.covers(Point(r["x"], r["y"])):
                continue
            link = LineString([(row["x"], row["y"]), (r["x"], r["y"])])
            if any(
                link.crosses(LineString([line["start"], line["end"]])) for line in segments or []
            ):
                continue
            value = _value(key, r["text"])
            if value:
                nearby.append((dx * dx + dy * dy, r, value))
        if nearby:
            _, r, value = min(nearby, key=lambda item: item[0])
            _assign(sheet, key, value, r)
    # A unique, explicit scale remains useful in a frame-less synthetic/PDF plan.
    scales = [
        (r, _value("scale", match[0]))
        for r in rows
        if not r.get("table_cell") and len(r["text"]) <= 80
        for match in _SCALE.finditer(r["text"])
    ]
    scales += [
        (r, _value("scale", r["text"]))
        for r in rows
        if r["text"].strip().upper() == "NTS" or r["text"].strip() == "لا يوجد مقياس"
    ]
    unique = {v for _, v in scales if v}
    if len(unique) == 1:
        r, v = next((r, v) for r, v in scales if v)
        _assign(sheet, "scale", v, r)
    _discipline(sheet)


def _discipline(sheet: Sheet):
    if sheet.number:
        hint = _DISCIPLINES.get(sheet.number.split("-")[0].upper())
        if hint:
            sheet.discipline_hint = hint
            sheet.source["discipline_hint"] = sheet.source["number"]


_METRES = {
    1: 0.0254,
    2: 0.3048,
    3: 1609.344,
    4: 0.001,
    5: 0.01,
    6: 1.0,
    7: 1000.0,
    10: 0.9144,
    14: 0.1,
}


# Conservative semantic room labels. Arbitrary alphabetic notes are not rooms.
_ROOM = re.compile(
    r"\b(?:room|office|bedroom|living|kitchen|bathroom|toilet|wc|wash|lobby|corridor|hall"
    r"|store|storage|service|entrance|reception|balcony|terrace|stair|parking|garage|gym"
    r"|classroom|pantry|dining|meeting|lounge|laundry|shaft)\b"
    r"|(?:غرف[ةه]|مكتب|مكاتب|معارض|مطبخ|حمام|صالة|صاله|دورة مياه|دورات مياه"
    r"|ممر|مدخل|مخزن|استقبال|بلكونة|سلم|خدمات)",
    re.I,
)
_NOTE = re.compile(
    r"\b(?:note|provide|install|typical|detail|schedule|plan|section|elevation|legend|floor|level|scale)\b|ملاحظ|تفصيل|مخطط|منسوب",
    re.I,
)


def _room_name(row: dict) -> bool:
    name = row["text"].strip()
    return bool(
        len(name) <= 60
        and _ROOM.search(name)
        and not _NOTE.search(name)
        and not _label(name)
        and not row.get("table_cell")
        and not _EXCLUDE.search(row.get("block", "") + row.get("layer", ""))
    )


def _rooms(sheet: Sheet, outlines: list[dict], units: int):
    polygons, seen = [], set()
    for row in outlines:
        if _EXCLUDE.search(row.get("layer", "") + row.get("block", "")):
            continue
        vertices = row.get("vertices", [])
        if len(vertices) < 3:
            continue
        polygon = Polygon(vertices)
        if polygon.is_valid and polygon.area > 0:
            identity = polygon.normalize().wkb
            if identity not in seen:
                seen.add(identity)
                polygons.append((polygon, row))
    names = [t for t in sheet.texts if _room_name(t)]
    tree = STRtree([p for p, _ in polygons])
    occupants = [[] for _ in polygons]
    for text in names:
        for i in tree.query(Point(text["x"], text["y"]), predicate="within"):
            occupants[i].append(text)
    selected = {}
    for i, texts in enumerate(occupants):
        if len(texts) == 1:
            text = texts[0]
            previous = selected.get(id(text))
            if previous is None or polygons[i][0].area < polygons[previous][0].area:
                selected[id(text)] = i
    for i in selected.values():
        polygon, outline = polygons[i]
        text = occupants[i][0]
        factor = _METRES.get(units)
        area = outline.get("area", polygon.area) * factor**2 if factor else None
        # Reject tiny symbol enclosures and building/site boundaries in known units.
        if area is not None and not 1 <= area <= 10000:
            continue
        sheet.rooms.append(
            Room(
                text["text"].strip(),
                area,
                list(polygon.bounds),
                {"name": _source(text), "outline": _source(outline), "units": units},
            )
        )


def sheets_from_drawing(drawing: Drawing) -> list[Sheet]:
    names = {
        r.get("layout", "Model")
        for key in ("texts", "inserts", "closed", "dimensions", "hatches")
        for r in getattr(drawing, key)
    } | {"Model"}
    names |= {layout["name"] for layout in drawing.layouts}
    result = []
    for name in sorted(names, key=lambda n: (n != "Model", n)):
        sheet = Sheet(layout=name)
        sheet.texts = [decode_text(t) for t in drawing.texts if t.get("layout", "Model") == name]
        inserts = [i for i in drawing.inserts if i.get("layout", "Model") == name]
        outlines = [o for o in drawing.closed if o.get("layout", "Model") == name]
        legend_regions = []
        for i in inserts:
            if (
                re.search(r"legend|table|schedule|جدول|مفتاح", i["block"], re.I)
                and len(i.get("bounds", [])) == 4
            ):
                x0, y0, x1, y1 = i["bounds"]
                if x1 > x0 and y1 > y0:
                    legend_regions.append(Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))
        legend_labels = [
            t
            for t in sheet.texts
            if re.search(r"\b(?:legend|schedule of symbols)\b|مفتاح الرموز", t["text"], re.I)
        ]
        for t in legend_labels:
            regions = []
            for o in outlines:
                if len(o.get("vertices", [])) >= 3:
                    p = Polygon(o["vertices"])
                    if p.is_valid and p.covers(Point(t["x"], t["y"])):
                        regions.append(p)
            if regions:
                legend_regions.append(min(regions, key=lambda p: p.area))
        installed = []
        for i in inserts:
            effective = i.get("effective_name", i["block"])
            if (
                effective.startswith("*")
                or _EXCLUDE.search(effective)
                or _EXCLUDE.search(i.get("container", "") + i.get("context", ""))
            ):
                continue
            if any(p.covers(Point(i["x"], i["y"])) for p in legend_regions):
                continue
            installed.append(i)
        sheet.counts = dict(Counter(i.get("effective_name", i["block"]) for i in installed))
        sheet.source["counts"] = [_source(i) for i in installed]
        sheet.counts_complete = not (drawing.omitted.get("inserts") or drawing.traversal_limited)
        sheet.rooms_complete = not (
            drawing.omitted.get("texts")
            or drawing.omitted.get("closed")
            or drawing.traversal_limited
        )
        points = [(t["x"], t["y"]) for t in sheet.texts + inserts] + [
            tuple(v[:2]) for o in outlines for v in o.get("vertices", [])
        ]
        bounds = (
            (
                min(x for x, y in points),
                min(y for x, y in points),
                max(x for x, y in points),
                max(y for x, y in points),
            )
            if points
            else (0, 0, 1, 1)
        )
        layout = next((layout for layout in drawing.layouts if layout["name"] == name), {})
        paper = layout.get("paper_size", [])
        if len(paper) == 2 and all(paper):
            bounds = (0, 0, *paper)
        _title(
            sheet,
            sheet.texts,
            inserts,
            bounds,
            outlines,
            _value("number", Path(drawing.name).stem),
            [line for line in drawing.segments if line.get("layout", "Model") == name],
        )
        if sheet.discipline_hint is None:
            evidence = [
                (r, _DISCIPLINES.get(r.get("layer", "").upper().split("-")[0]))
                for r in sheet.texts + inserts + outlines
            ]
            hints = {hint for _, hint in evidence if hint}
            if len(hints) == 1:
                row, sheet.discipline_hint = next((r, h) for r, h in evidence if h)
                sheet.source["discipline_hint"] = {**_source(row), "layer": row["layer"]}
        room_outlines = outlines
        if name == "Model" and len(drawing.extents) == 4:
            x0, y0, x1, y1 = drawing.extents
            if x1 > x0 and y1 > y0:
                room_outlines = [
                    o
                    for o in outlines
                    if o.get("vertices")
                    and all(x0 <= v[0] <= x1 and y0 <= v[1] <= y1 for v in o["vertices"])
                ]
        if sheet.rooms_complete:
            _rooms(sheet, room_outlines, drawing.units)
        if _non_plan(sheet.title) or _non_plan(drawing.name):
            sheet.rooms = []
        if sheet.number is None and drawing.name:
            number = _value("number", Path(drawing.name).stem)
            if number:
                sheet.number = number
                sheet.source["number"] = {"source": "file name", "name": drawing.name}
                _discipline(sheet)
        result.append(sheet)
    paper_titles = [s.title for s in result if s.layout != "Model" and s.title]
    model = next(s for s in result if s.layout == "Model")
    if paper_titles and all(_non_plan(title) for title in paper_titles):
        model.rooms = []
    if paper_titles and all(
        re.search(r"legend|schedule|جدول|مفتاح", title, re.I) for title in paper_titles
    ):
        model.counts = {}
        model.source["counts"] = []
    return result


def _non_plan(title: str | None) -> bool:
    return bool(
        title
        and re.search(r"legend|diagram|schedule|notes|details|جدول|تفاصيل|ملاحظات", title, re.I)
    )


def read_sheets(name: str, data: bytes) -> list[Sheet]:
    drawing = read_drawing(name, data)
    if drawing.note and not drawing.repaired:
        return []
    sheets = sheets_from_drawing(drawing)
    number = _value("number", Path(name).stem)
    if number:
        for sheet in sheets:
            if sheet.number is None:
                sheet.number = number
                sheet.source["number"] = {"source": "file name", "name": name}
                _discipline(sheet)
    return sheets


def read_pdf_sheet(
    words_with_boxes: list[dict],
    page_size: tuple,
    *,
    closed: list[dict] | None = None,
    metres_per_unit: float | None = None,
) -> Sheet:
    """Positioned text/OCR. PDF room areas require vector outlines AND explicit calibration.

    `closed` uses vertices in PDF coordinates. No scale is inferred from page pixels.
    """
    width, height = page_size
    rows = []
    for word in words_with_boxes:
        box = [word[k] for k in ("x0", "top", "x1", "bottom")]
        rows.append(
            {
                "text": word["text"],
                "x": box[0],
                "y": height - box[3],
                "box": box,
                "page": word.get("page", 1),
            }
        )
    # Join words sharing a baseline, retaining the union box for the source.
    lines = []
    for row in sorted(rows, key=lambda r: (r["box"][1], r["x"])):
        if (
            lines
            and abs(lines[-1]["box"][1] - row["box"][1]) <= 2
            and lines[-1]["page"] == row["page"]
        ):
            line = lines[-1]
            if re.search(r"[\u0621-\u064a]", line["text"] + row["text"]):
                line["text"] = row["text"] + " " + line["text"]
            else:
                line["text"] += " " + row["text"]
            line["box"] = [
                min(line["box"][0], row["box"][0]),
                min(line["box"][1], row["box"][1]),
                max(line["box"][2], row["box"][2]),
                max(line["box"][3], row["box"][3]),
            ]
        else:
            lines.append(dict(row))
    sheet = Sheet(layout="PDF", texts=lines)
    _title(sheet, lines, [], (0, 0, width, height))
    if closed:
        outlines = []
        for vector in closed:
            vertices = vector.get("vertices", [])
            if len(vertices) < 3:
                continue
            xs, ys = zip(*vertices, strict=True)
            outlines.append(
                {
                    **vector,
                    "page": vector.get("page", 1),
                    "box": vector.get("box", [min(xs), min(ys), max(xs), max(ys)]),
                    "vertices": [[x, height - y] for x, y in vertices],
                }
            )
        _rooms(sheet, outlines, 0)
        if metres_per_unit is not None and metres_per_unit > 0:
            for room in sheet.rooms:
                outline = next(o for o in outlines if _source(o) == room.source["outline"])
                room.area_m2 = Polygon(outline["vertices"]).area * metres_per_unit**2
                room.source["calibration"] = metres_per_unit
    return sheet


def _embedded_texts(drawing: Drawing):
    """Read cached Excel cells from OLE storage without executing embedded code."""
    import xlrd

    for embedded in drawing.embedded:
        if embedded.get("package_hex"):
            _package_texts(drawing, embedded)
            _deduplicate_cells(drawing)
            continue
        payload = embedded.get("compound_hex", "")
        if not payload or len(payload) > 16 * 1024 * 1024:
            continue
        try:
            book = xlrd.open_workbook(file_contents=bytes.fromhex(payload), on_demand=True)
            try:
                for table in book.sheets():
                    for ri in range(min(table.nrows, 4096)):
                        for ci in range(min(table.ncols, 256)):
                            cell = table.cell(ri, ci)
                            if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                                continue
                            value = str(cell.value)
                            drawing.texts.append(
                                {
                                    k: v
                                    for k, v in embedded.items()
                                    if k not in ("compound_hex", "package_hex")
                                }
                                | {
                                    "text": value,
                                    "raw_text": value,
                                    "table_cell": [ri, ci],
                                    "embedded_sheet": table.name,
                                }
                            )
                            if len(drawing.texts) >= 100000:
                                drawing.problems.append({"code": "embedded-cell-limit"})
                                return
            finally:
                book.release_resources()
                _deduplicate_cells(drawing)
        except (ValueError, xlrd.XLRDError, IndexError, TypeError):
            drawing.problems.append(
                {"code": "embedded-workbook-unreadable", "handle": embedded.get("handle")}
            )


def _package_texts(drawing: Drawing, embedded: dict):
    import io
    import zipfile

    import openpyxl

    payload = embedded["package_hex"]
    if len(payload) > 16 * 1024 * 1024:
        return
    try:
        data = bytes.fromhex(payload)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 64 * 1024 * 1024:
                return
        book = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=True, keep_links=False
        )
        try:
            source = {k: v for k, v in embedded.items() if k not in ("compound_hex", "package_hex")}
            for table in book:
                for ri, row in enumerate(
                    table.iter_rows(
                        max_row=min(table.max_row or 4096, 4096),
                        max_col=min(table.max_column or 256, 256),
                        values_only=True,
                    )
                ):
                    for ci, value in enumerate(row):
                        if value is None:
                            continue
                        drawing.texts.append(
                            source
                            | {
                                "text": str(value),
                                "raw_text": str(value),
                                "table_cell": [ri, ci],
                                "embedded_sheet": table.title,
                            }
                        )
                        if len(drawing.texts) >= 100000:
                            drawing.problems.append({"code": "embedded-cell-limit"})
                            return
        finally:
            book.close()
    except (ValueError, OSError, KeyError, zipfile.BadZipFile):
        drawing.problems.append(
            {"code": "embedded-workbook-unreadable", "handle": embedded.get("handle")}
        )


def _deduplicate_cells(drawing: Drawing):
    # OLE placements often embed the entire same workbook many times. Retain
    # the first sourced occurrence of each identical cell/value per layout.
    seen, rows = set(), []
    for row in drawing.texts:
        if "embedded_sheet" in row:
            key = (
                row.get("layout", "Model"),
                row["embedded_sheet"],
                tuple(row["table_cell"]),
                row["text"],
            )
            if key in seen:
                continue
            seen.add(key)
        rows.append(row)
    drawing.texts = rows
